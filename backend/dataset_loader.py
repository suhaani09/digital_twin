
"""
MIT-BIH Arrhythmia Dataset Loader & Preprocessing Pipeline.

Ensures:
- Safe ingestion using wfdb or local cache.
- Preservation of raw signal arrays and header metadata.
- AAMI EC57 class mapping:
  - N: Normal beat (N, L, R, e, j)
  - S: Supraventricular ectopic (A, a, J, S)
  - V: Ventricular ectopic (V, E)
  - F: Fusion of ventricular and normal (F)
  - Q: Unclassifiable / Paced (/ , f, Q)
- Window segmentation centered around R-peaks (e.g. 90 samples before, 110 after at 360 Hz = ~555 ms window).
- Patient-level split isolation (preventing subject leakage between Train / Val / Test).
"""

from dataclasses import dataclass
import os
from typing import Dict, List, Optional, Tuple
import numpy as np
import wfdb

from backend.ecg_processor import (
    assess_signal_quality,
    butter_bandpass_filter,
    extract_beat_features,
    generate_synthetic_ecg,
)

# Standard AAMI 1998 mapping
AAMI_MAPPING = {
    "N": "N", "L": "N", "R": "N", "e": "N", "j": "N",
    "A": "S", "a": "S", "J": "S", "S": "S",
    "V": "V", "E": "V",
    "F": "F",
    "/": "Q", "f": "Q", "Q": "Q",
}

# Standard inter-patient division based on De Chazal et al. (2004)
DE_CHAZAL_DS1_TRAIN = [
    "101", "106", "108", "109", "112", "114", "115", "116", "118", "119",
    "122", "124", "201", "203", "205", "207", "208", "209", "215", "220", "223", "230",
]
DE_CHAZAL_DS2_TEST = [
    "100", "103", "105", "111", "113", "117", "121", "123", "200", "202",
    "210", "212", "213", "214", "219", "221", "222", "228", "231", "232", "233", "234",
]


@dataclass
class BeatSegment:
    patient_id: str
    r_sample: int
    timestamp_sec: float
    raw_window: np.ndarray
    filtered_window: np.ndarray
    original_symbol: str
    aami_class: str
    features: np.ndarray


@dataclass
class ECGRecordData:
    record_name: str
    fs: float
    lead_names: List[str]
    raw_signal: np.ndarray  # Shape: (N_samples, N_leads)
    filtered_signal: np.ndarray
    r_peaks: np.ndarray
    symbols: List[str]
    is_synthetic: bool = False


class MITBIHLoader:
    """Robust loader for MIT-BIH Arrhythmia Database with caching and synthetic fallback."""

    def __init__(self, data_dir: str = "data/mitdb"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def load_record(
        self,
        record_id: str,
        max_samples: Optional[int] = None,
        use_cache: bool = False,
    ) -> ECGRecordData:
        """Loads a single record, downloads if missing, and applies non-destructive filtering."""
        try:
            # Check local file existence first
            hea_path = os.path.join(self.data_dir, f"{record_id}.hea")
            dat_path = os.path.join(self.data_dir, f"{record_id}.dat")

            if os.path.exists(hea_path) and os.path.exists(dat_path):
                rec = wfdb.rdrecord(os.path.join(self.data_dir, record_id), sampto=max_samples)
                ann = wfdb.rdann(os.path.join(self.data_dir, record_id), "atr", sampto=max_samples)
            else:
                # Online download from PhysioNet mitdb with max_samples constraint
                rec = wfdb.rdrecord(record_id, pn_dir="mitdb", sampto=max_samples or 3600)
                ann = wfdb.rdann(record_id, "atr", pn_dir="mitdb", sampto=max_samples or 3600)

            raw_signal = np.copy(rec.p_signal)
            lead_idx = 0  # MLII is usually lead 0
            filtered_lead = butter_bandpass_filter(raw_signal[:, lead_idx], fs=rec.fs)

            filtered_signal = np.copy(raw_signal)
            filtered_signal[:, lead_idx] = filtered_lead

            return ECGRecordData(
                record_name=str(record_id),
                fs=float(rec.fs),
                lead_names=rec.sig_name,
                raw_signal=raw_signal,
                filtered_signal=filtered_signal,
                r_peaks=np.array(ann.sample, dtype=int),
                symbols=list(ann.symbol),
                is_synthetic=False,
            )

        except Exception as e:
            # Fallback to clearly labeled synthetic record to ensure testability without network
            return self.create_synthetic_record(record_id=f"SYNTH_{record_id}")

    def create_synthetic_record(
        self,
        record_id: str = "SYNTH_FIXTURE_100",
        duration_sec: float = 60.0,
        fs: float = 360.0,
        bpm: float = 75.0,
    ) -> ECGRecordData:
        """Generates a synthetic fixture for deterministic unit testing & offline dev."""
        ecg_raw, r_peaks, symbols = generate_synthetic_ecg(
            duration_sec=duration_sec,
            fs=fs,
            bpm=bpm,
            noise_amplitude=0.03,
            add_ectopic=True,
        )
        filtered_ecg = butter_bandpass_filter(ecg_raw, fs=fs)
        raw_2d = np.column_stack([ecg_raw, ecg_raw * 0.5])
        filt_2d = np.column_stack([filtered_ecg, filtered_ecg * 0.5])

        return ECGRecordData(
            record_name=record_id,
            fs=fs,
            lead_names=["MLII_SYNTH", "V5_SYNTH"],
            raw_signal=raw_2d,
            filtered_signal=filt_2d,
            r_peaks=r_peaks,
            symbols=symbols,
            is_synthetic=True,
        )

    def segment_record(
        self,
        record: ECGRecordData,
        lead_idx: int = 0,
        pre_r_samples: int = 90,
        post_r_samples: int = 110,
    ) -> List[BeatSegment]:
        """Segments record into QRS windows (pre_r + post_r = 200 samples ~ 555 ms)."""
        raw_sig = record.raw_signal[:, lead_idx]
        filt_sig = record.filtered_signal[:, lead_idx]
        fs = record.fs

        r_peaks = record.r_peaks
        symbols = record.symbols
        segments = []

        total_samples = len(raw_sig)

        for i, (r_pos, sym) in enumerate(zip(r_peaks, symbols)):
            # Discard non-beat annotation symbols like '+' or '~'
            if sym not in AAMI_MAPPING:
                continue

            aami_class = AAMI_MAPPING[sym]
            start = r_pos - pre_r_samples
            end = r_pos + post_r_samples

            # Bound checks
            if start < 0 or end > total_samples:
                continue

            # RR interval metrics (in seconds)
            pre_rr = (r_pos - r_peaks[i - 1]) / fs if i > 0 else 0.8
            post_rr = (r_peaks[i + 1] - r_pos) / fs if i < len(r_peaks) - 1 else 0.8

            # Local RR mean (window of 5 beats)
            local_start = max(0, i - 2)
            local_end = min(len(r_peaks), i + 3)
            local_diffs = np.diff(r_peaks[local_start:local_end]) / fs
            local_rr_mean = float(np.mean(local_diffs)) if len(local_diffs) > 0 else 0.8

            raw_window = raw_sig[start:end]
            filt_window = filt_sig[start:end]

            # Features from filtered window
            feats = extract_beat_features(
                window=filt_window,
                pre_r_rr=pre_rr,
                post_r_rr=post_rr,
                local_rr_mean=local_rr_mean,
                fs=fs,
            )

            segments.append(
                BeatSegment(
                    patient_id=record.record_name,
                    r_sample=int(r_pos),
                    timestamp_sec=round(float(r_pos / fs), 4),
                    raw_window=raw_window,
                    filtered_window=filt_window,
                    original_symbol=sym,
                    aami_class=aami_class,
                    features=feats,
                )
            )

        return segments
