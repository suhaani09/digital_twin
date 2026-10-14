"""
ECG Signal Processing Pipeline & Feature Extraction Engine.

Handles:
- Bandpass filtering (0.5 - 45 Hz Butterworth) to eliminate baseline wander and high-frequency noise.
- Notch filtering (50/60 Hz power-line interference).
- Signal Quality Index (SQI) checks and missing/flatline validation.
- Real-time Pan-Tompkins QRS peak detection.
- Morphological & statistical feature extraction for beat windows.
- Synthetic ECG generation (ECGSYN-style) for fallback / isolated testing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.signal import butter, filtfilt, iirnotch


@dataclass
class SignalQualityResult:
    is_valid: bool
    snr_db: float
    flatline_ratio: float
    missing_ratio: float
    status: str
    details: Dict[str, float] = field(default_factory=dict)


def butter_bandpass_filter(
    data: np.ndarray,
    lowcut: float = 0.5,
    highcut: float = 45.0,
    fs: float = 360.0,
    order: int = 3,
) -> np.ndarray:
    """Zero-phase Butterworth bandpass filter to remove baseline wander and HF noise."""
    nyq = 0.5 * fs
    low = max(0.001, lowcut / nyq)
    high = min(0.999, highcut / nyq)
    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, data)


def notch_filter(
    data: np.ndarray,
    freq: float = 50.0,
    fs: float = 360.0,
    quality_factor: float = 30.0,
) -> np.ndarray:
    """IIR Notch filter to eliminate powerline interference (50 Hz or 60 Hz)."""
    nyq = 0.5 * fs
    if freq >= nyq:
        return data
    w0 = freq / nyq
    b, a = iirnotch(w0, quality_factor)
    return filtfilt(b, a, data)


def assess_signal_quality(
    signal: np.ndarray,
    fs: float = 360.0,
    flatline_thresh: float = 1e-4,
) -> SignalQualityResult:
    """
    Assesses signal quality without modifying original arrays:
    - Missing / NaN ratio
    - Flatline / lead disconnection ratio
    - Estimated Signal-to-Noise Ratio (SNR) proxy
    """
    if len(signal) == 0:
        return SignalQualityResult(
            is_valid=False,
            snr_db=-99.0,
            flatline_ratio=1.0,
            missing_ratio=1.0,
            status="EMPTY_SIGNAL",
        )

    # Missing check
    nan_mask = np.isnan(signal) | np.isinf(signal)
    missing_ratio = float(np.mean(nan_mask))

    if missing_ratio > 0.1:
        return SignalQualityResult(
            is_valid=False,
            snr_db=-99.0,
            flatline_ratio=0.0,
            missing_ratio=missing_ratio,
            status="EXCESSIVE_MISSING_DATA",
        )

    # Clean temporary view for flatline calculation
    clean_sig = np.nan_to_num(signal, nan=0.0)
    diffs = np.abs(np.diff(clean_sig))
    flatline_ratio = float(np.mean(diffs < flatline_thresh))

    if flatline_ratio > 0.6:
        return SignalQualityResult(
            is_valid=False,
            snr_db=-10.0,
            flatline_ratio=flatline_ratio,
            missing_ratio=missing_ratio,
            status="LEAD_OFF_OR_FLATLINE",
        )

    # Simple Power SQI (QRS band power 5-20Hz vs total power)
    var_total = float(np.var(clean_sig))
    if var_total < 1e-6:
        return SignalQualityResult(
            is_valid=False,
            snr_db=-30.0,
            flatline_ratio=flatline_ratio,
            missing_ratio=missing_ratio,
            status="NEAR_ZERO_POWER",
        )

    try:
        band_qrs = butter_bandpass_filter(clean_sig, lowcut=5.0, highcut=20.0, fs=fs, order=2)
        var_qrs = float(np.var(band_qrs))
        snr_proxy = 10.0 * np.log10(max(1e-6, var_qrs) / max(1e-6, var_total - var_qrs + 1e-6))
    except Exception:
        snr_proxy = 10.0

    is_valid = bool(missing_ratio < 0.05 and flatline_ratio < 0.4 and snr_proxy > -15.0)
    status = "ACCEPTABLE" if is_valid else "POOR_QUALITY"

    return SignalQualityResult(
        is_valid=is_valid,
        snr_db=round(snr_proxy, 2),
        flatline_ratio=round(flatline_ratio, 4),
        missing_ratio=round(missing_ratio, 4),
        status=status,
        details={"var_total": var_total},
    )


class PanTompkinsDetector:
    """
    Classical Pan-Tompkins QRS Peak Detection Algorithm (1985).
    Deterministic, zero-parameter-hallucination real-time QRS detector.
    """

    def __init__(self, fs: float = 360.0):
        self.fs = fs

    def detect_peaks(self, signal: np.ndarray) -> np.ndarray:
        """
        Executes:
        1. Bandpass filter (5 - 15 Hz)
        2. Derivative filter (d/dt)
        3. Squaring function
        4. Moving window integration (~150 ms window)
        5. Adaptive threshold peak detection
        """
        if len(signal) < int(self.fs):
            return np.array([], dtype=int)

        # 1. Bandpass 5-15 Hz
        b_bp, a_bp = butter(1, [5.0 / (0.5 * self.fs), 15.0 / (0.5 * self.fs)], btype="band")
        filtered = filtfilt(b_bp, a_bp, signal)

        # 2. Derivative
        diff = np.diff(filtered)
        diff = np.append(diff, 0)

        # 3. Squaring
        squared = diff**2

        # 4. Moving window integration (approx 150 ms)
        win_size = int(0.15 * self.fs)
        kernel = np.ones(win_size) / win_size
        integrated = np.convolve(squared, kernel, mode="same")

        # 5. Thresholding & Peak finding (min distance 200ms -> refractory period)
        min_dist = int(0.25 * self.fs)
        threshold = 0.35 * np.mean(integrated) + 0.15 * np.max(integrated)

        candidate_peaks = []
        for i in range(1, len(integrated) - 1):
            if integrated[i] > threshold and integrated[i] > integrated[i - 1] and integrated[i] > integrated[i + 1]:
                if not candidate_peaks or (i - candidate_peaks[-1]) >= min_dist:
                    candidate_peaks.append(i)

        # Refine peaks to find actual local maxima in the bandpassed signal
        refined_peaks = []
        search_radius = int(0.08 * self.fs)
        for cp in candidate_peaks:
            start = max(0, cp - search_radius)
            end = min(len(signal), cp + search_radius)
            local_max = start + np.argmax(np.abs(signal[start:end]))
            if not refined_peaks or (local_max - refined_peaks[-1]) >= min_dist:
                refined_peaks.append(local_max)

        return np.array(refined_peaks, dtype=int)


def extract_beat_features(
    window: np.ndarray,
    pre_r_rr: float,
    post_r_rr: float,
    local_rr_mean: float,
    fs: float = 360.0,
) -> np.ndarray:
    """
    Extracts a feature vector for a single segmented QRS window:
    - Morphological features: amplitude stats, energy, kurtosis, skewness
    - Interval & rhythm features: pre-RR, post-RR, local-RR ratio
    Total dimension: 16 features.
    """
    mean_val = float(np.mean(window))
    std_val = float(np.std(window)) + 1e-8
    centered = window - mean_val

    # Statistical moments
    skewness = float(np.mean((centered / std_val) ** 3))
    kurt = float(np.mean((centered / std_val) ** 4))
    energy = float(np.sum(window**2) / len(window))
    peak_to_peak = float(np.ptp(window))
    max_val = float(np.max(window))
    min_val = float(np.min(window))

    # Segment derivatives
    diff = np.diff(window)
    mean_deriv = float(np.mean(np.abs(diff)))
    max_deriv = float(np.max(np.abs(diff))) if len(diff) > 0 else 0.0

    # Rhythm ratios
    rr_ratio = pre_r_rr / (local_rr_mean + 1e-5)
    rr_delta = pre_r_rr - post_r_rr

    features = [
        mean_val,
        std_val,
        skewness,
        kurt,
        energy,
        peak_to_peak,
        max_val,
        min_val,
        mean_deriv,
        max_deriv,
        pre_r_rr,
        post_r_rr,
        local_rr_mean,
        rr_ratio,
        rr_delta,
        float(len(window)),
    ]
    return np.array(features, dtype=np.float32)


def generate_synthetic_ecg(
    duration_sec: float = 10.0,
    fs: float = 360.0,
    bpm: float = 72.0,
    noise_amplitude: float = 0.02,
    add_ectopic: bool = False,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """
    Procedural synthetic ECG generator for standalone testing and offline fixtures.
    Generates realistic P-Q-R-S-T waves, R-peak annotations, and class labels.
    """
    total_samples = int(duration_sec * fs)
    t = np.linspace(0, duration_sec, total_samples, endpoint=False)
    ecg = np.zeros(total_samples)

    rr_interval = 60.0 / bpm
    r_peaks = []
    labels = []

    current_time = 0.4  # offset
    beat_idx = 0

    while current_time < duration_sec - 0.4:
        # Every 6th beat optionally make a Premature Ventricular Contraction (V)
        is_pvc = add_ectopic and (beat_idx % 6 == 5)
        beat_type = "V" if is_pvc else "N"

        r_sample = int(current_time * fs)
        r_peaks.append(r_sample)
        labels.append(beat_type)

        if not is_pvc:
            # Normal beat
            p_amp, p_width, p_dt = 0.15, 0.04, -0.16
            q_amp, q_width, q_dt = -0.15, 0.015, -0.04
            r_amp, r_width, r_dt = 1.0, 0.025, 0.0
            s_amp, s_width, s_dt = -0.25, 0.02, 0.04
            t_amp, t_width, t_dt = 0.3, 0.07, 0.22

            waves = [(p_amp, p_width, p_dt), (q_amp, q_width, q_dt),
                     (r_amp, r_width, r_dt), (s_amp, s_width, s_dt),
                     (t_amp, t_width, t_dt)]
        else:
            # Wide, inverted/biphasic PVC waveform
            r_amp, r_width, r_dt = -0.9, 0.06, 0.0
            t_amp, t_width, t_dt = 0.45, 0.09, 0.25
            waves = [(r_amp, r_width, r_dt), (t_amp, t_width, t_dt)]

        for amp, width, dt in waves:
            center = current_time + dt
            ecg += amp * np.exp(-((t - center) ** 2) / (2 * width**2))

        # Advance time
        if is_pvc:
            current_time += rr_interval * 0.7  # Premature
        else:
            current_time += rr_interval

        beat_idx += 1

    # Add realistic baseline wander and noise
    baseline_wander = 0.05 * np.sin(2 * np.pi * 0.25 * t)
    noise = noise_amplitude * np.random.normal(0, 1, total_samples)
    ecg += baseline_wander + noise

    return ecg, np.array(r_peaks, dtype=int), labels

