"""
Unit and Integration Tests for ECG Pipeline & ML Subsystem.

Tests:
1. Signal loading and metadata preservation (raw vs filtered).
2. Sampling rate verification and multi-lead shape checks.
3. Signal quality index (SQI) detection: clean, flatline, NaN/inf.
4. Deterministic Pan-Tompkins QRS peak detection.
5. Window segmentation and sample length constraints (200 samples = ~555 ms).
6. Missing value handling and non-destructive filtering.
7. Structured prediction format and metadata verification.
8. Patient split leakage verification (disjoint patient ID sets).
"""

import numpy as np
import pytest

from backend.dataset_loader import (
    AAMI_MAPPING,
    DE_CHAZAL_DS1_TRAIN,
    DE_CHAZAL_DS2_TEST,
    BeatSegment,
    MITBIHLoader,
)
from backend.classifier import ECGClassifierService, StructuredECGPrediction
from backend.ecg_processor import (
    PanTompkinsDetector,
    assess_signal_quality,
    butter_bandpass_filter,
    generate_synthetic_ecg,
)


class TestSignalProcessingAndSQI:

    def test_synthetic_ecg_generation_and_shape(self):
        duration = 5.0
        fs = 360.0
        ecg, r_peaks, labels = generate_synthetic_ecg(duration_sec=duration, fs=fs, bpm=60.0)

        assert len(ecg) == int(duration * fs)
        assert len(r_peaks) >= 4
        assert len(r_peaks) == len(labels)
        assert "N" in labels

    def test_bandpass_filter_preserves_length(self):
        data = np.random.normal(0, 1, 1000)
        filtered = butter_bandpass_filter(data, lowcut=0.5, highcut=45.0, fs=360.0)
        assert len(filtered) == len(data)
        assert not np.isnan(filtered).any()

    def test_sqi_clean_signal(self):
        ecg, _, _ = generate_synthetic_ecg(duration_sec=5.0, fs=360.0, noise_amplitude=0.01)
        sqi = assess_signal_quality(ecg, fs=360.0)
        assert sqi.is_valid is True
        assert sqi.status == "ACCEPTABLE"
        assert sqi.missing_ratio == 0.0
        assert sqi.flatline_ratio < 0.2

    def test_sqi_detects_flatline_lead_off(self):
        flatline = np.zeros(1000)
        sqi = assess_signal_quality(flatline, fs=360.0)
        assert sqi.is_valid is False
        assert sqi.status in ["LEAD_OFF_OR_FLATLINE", "NEAR_ZERO_POWER"]

    def test_sqi_detects_nans_and_missing(self):
        sig = np.random.normal(0, 1, 1000)
        sig[100:300] = np.nan
        sqi = assess_signal_quality(sig, fs=360.0)
        assert sqi.is_valid is False
        assert sqi.status == "EXCESSIVE_MISSING_DATA"

    def test_pan_tompkins_peak_detector(self):
        ecg, ground_truth_peaks, _ = generate_synthetic_ecg(duration_sec=6.0, fs=360.0, bpm=72.0)
        detector = PanTompkinsDetector(fs=360.0)
        detected_peaks = detector.detect_peaks(ecg)

        assert len(detected_peaks) > 0
        # Check that detected peaks are within 50 ms (18 samples) of ground truth
        matched = 0
        for gt in ground_truth_peaks:
            if np.min(np.abs(detected_peaks - gt)) < 18:
                matched += 1
        sensitivity = matched / len(ground_truth_peaks)
        assert sensitivity >= 0.85, f"Expected >85% detection sensitivity, got {sensitivity}"


class TestDatasetLoaderAndSplits:

    def test_patient_cohort_splits_are_strictly_disjoint(self):
        train_set = set(DE_CHAZAL_DS1_TRAIN)
        test_set = set(DE_CHAZAL_DS2_TEST)
        overlap = train_set.intersection(test_set)
        assert len(overlap) == 0, f"Data leakage detected! Overlapping subjects: {overlap}"

    def test_synthetic_record_creation_and_segmentation(self):
        loader = MITBIHLoader()
        rec = loader.create_synthetic_record(record_id="TEST_SYNTH_01", duration_sec=10.0, fs=360.0)

        assert rec.is_synthetic is True
        assert rec.fs == 360.0
        assert rec.raw_signal.shape[1] == 2
        assert len(rec.r_peaks) == len(rec.symbols)

        segments = loader.segment_record(rec, lead_idx=0, pre_r_samples=90, post_r_samples=110)
        assert len(segments) > 0

        for seg in segments:
            assert len(seg.raw_window) == 200
            assert len(seg.filtered_window) == 200
            assert seg.aami_class in ["N", "S", "V", "F", "Q"]
            assert len(seg.features) == 16
            assert not np.isnan(seg.features).any()

    def test_loader_does_not_mutate_raw_signal(self):
        loader = MITBIHLoader()
        rec = loader.create_synthetic_record(record_id="TEST_MUTATE_01")
        raw_copy = np.copy(rec.raw_signal)

        # Run segmentation and filtering
        _ = loader.segment_record(rec)

        # Assert raw signal was completely preserved
        np.testing.assert_array_equal(rec.raw_signal, raw_copy)


class TestClassifierService:

    def test_structured_prediction_format_clean_signal(self):
        service = ECGClassifierService()
        ecg, _, _ = generate_synthetic_ecg(duration_sec=2.0, fs=360.0)
        window = ecg[:200]

        pred: StructuredECGPrediction = service.predict_window(
            raw_window=window,
            patient_id="SYNTH_PATIENT_TEST",
            timestamp_sec=1.5,
            pre_rr=0.8,
            post_rr=0.8,
            local_rr_mean=0.8,
            fs=360.0,
        )

        assert isinstance(pred, StructuredECGPrediction)
        assert pred.patient_id == "SYNTH_PATIENT_TEST"
        assert pred.window_timestamp_sec == 1.5
        assert pred.predicted_class in ["N", "S", "V", "F", "Q", "POOR_QUALITY"]
        assert isinstance(pred.class_scores, dict)
        assert pred.is_calibrated_probability is False
        assert pred.signal_quality_status == "ACCEPTABLE"
        assert pred.inference_latency_ms >= 0.0

    def test_structured_prediction_rejects_poor_signal(self):
        service = ECGClassifierService()
        flat_window = np.zeros(200)

        pred = service.predict_window(
            raw_window=flat_window,
            patient_id="PATIENT_FLATLINE",
            timestamp_sec=10.0,
            fs=360.0,
        )

        assert pred.predicted_class == "POOR_QUALITY"
        assert pred.signal_quality_status in ["LEAD_OFF_OR_FLATLINE", "NEAR_ZERO_POWER"]
        assert pred.is_calibrated_probability is False

