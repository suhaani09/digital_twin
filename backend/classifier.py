"""
ECG Baseline Beat Classifier & Model Serving Service.

Features:
- Structured predictions with signal-quality and model provenance.
- Clean distinction between raw model output and calibrated probabilities.
- Rejection of low-quality or lead-off signals.
- Transparent serialization via joblib + JSON metadata.
"""

from dataclasses import asdict, dataclass
import json
import os
import time
from typing import Dict, List, Optional
import joblib
import numpy as np

from backend.ecg_processor import (
    assess_signal_quality,
    butter_bandpass_filter,
    extract_beat_features,
)


class GaussianNBBaseline:
    """
    Transparent, pure-NumPy Gaussian Naive Bayes Classifier.
    Zero C-thread deadlock issues, deterministic, reproducible baseline with probability estimates.
    """

    def __init__(self):
        self.classes_ = np.array([])
        self.mean_ = {}
        self.var_ = {}
        self.priors_ = {}

    def fit(self, X: np.ndarray, y: np.ndarray):
        self.classes_ = np.unique(y)
        self.mean_ = {}
        self.var_ = {}
        self.priors_ = {}
        n_total = len(X)
        for c in self.classes_:
            X_c = X[y == c]
            self.mean_[c] = np.mean(X_c, axis=0)
            self.var_[c] = np.var(X_c, axis=0) + 1e-4
            self.priors_[c] = len(X_c) / n_total
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        posteriors = []
        for c in self.classes_:
            prior = np.log(self.priors_[c] + 1e-9)
            likelihood = -0.5 * np.sum(np.log(2 * np.pi * self.var_[c])) - 0.5 * np.sum(
                ((X - self.mean_[c]) ** 2) / self.var_[c], axis=1
            )
            posteriors.append(prior + likelihood)
        posteriors = np.array(posteriors).T
        exp_p = np.exp(posteriors - np.max(posteriors, axis=1, keepdims=True))
        probs = exp_p / np.sum(exp_p, axis=1, keepdims=True)
        return probs

    def predict(self, X: np.ndarray) -> np.ndarray:
        probs = self.predict_proba(X)
        return self.classes_[np.argmax(probs, axis=1)]


@dataclass
class StructuredECGPrediction:
    patient_id: str
    window_timestamp_sec: float
    predicted_class: str
    class_label_meaning: str
    class_scores: Dict[str, float]
    is_calibrated_probability: bool
    signal_quality_status: str
    snr_db: float
    model_version: str
    data_provenance: str
    inference_latency_ms: float


CLASS_DESCRIPTIONS = {
    "N": "Normal / Bundle branch block beat",
    "S": "Supraventricular ectopic beat (e.g., PAC)",
    "V": "Ventricular ectopic beat (e.g., PVC)",
    "F": "Fusion beat",
    "Q": "Unknown / Paced beat",
}


class ECGClassifierService:
    """Inference wrapper for trained ECG beat classifier."""

    def __init__(self, model_dir: str = "backend/models"):
        self.model_dir = model_dir
        self.model = None
        self.scaler = None
        self.classes_ = ["N", "S", "V", "F", "Q"]
        self.metadata = {}
        self.load_model()

    def load_model(self) -> bool:
        model_path = os.path.join(self.model_dir, "ecg_classifier.joblib")
        meta_path = os.path.join(self.model_dir, "model_meta.json")

        if os.path.exists(model_path) and os.path.exists(meta_path):
            bundle = joblib.load(model_path)
            self.model = bundle["model"]
            self.scaler = bundle.get("scaler")
            self.classes_ = list(bundle.get("classes", self.classes_))
            with open(meta_path, "r") as f:
                self.metadata = json.load(f)
            return True
        return False

    def predict_window(
        self,
        raw_window: np.ndarray,
        patient_id: str = "PATIENT_UNKNOWN",
        timestamp_sec: float = 0.0,
        pre_rr: float = 0.8,
        post_rr: float = 0.8,
        local_rr_mean: float = 0.8,
        fs: float = 360.0,
    ) -> StructuredECGPrediction:
        """
        Runs signal quality evaluation, non-destructive filtering,
        feature extraction, and structured classification.
        """
        start_t = time.perf_counter()

        # 1. Signal quality assessment
        sqi = assess_signal_quality(raw_window, fs=fs)

        if not sqi.is_valid:
            latency = (time.perf_counter() - start_t) * 1000.0
            return StructuredECGPrediction(
                patient_id=patient_id,
                window_timestamp_sec=timestamp_sec,
                predicted_class="POOR_QUALITY",
                class_label_meaning=f"Signal degraded: {sqi.status}",
                class_scores={c: 0.0 for c in self.classes_},
                is_calibrated_probability=False,
                signal_quality_status=sqi.status,
                snr_db=sqi.snr_db,
                model_version=self.metadata.get("version", "v1.0.0-baseline"),
                data_provenance=self.metadata.get("dataset", "MIT-BIH / Synthetic Fixture"),
                inference_latency_ms=round(latency, 2),
            )

        # 2. Filter window
        try:
            filt_window = butter_bandpass_filter(raw_window, fs=fs)
        except Exception:
            filt_window = raw_window

        # 3. Extract features
        feats = extract_beat_features(
            window=filt_window,
            pre_r_rr=pre_rr,
            post_r_rr=post_rr,
            local_rr_mean=local_rr_mean,
            fs=fs,
        ).reshape(1, -1)

        # Scale if scaler exists
        if self.scaler is not None:
            feats = self.scaler.transform(feats)

        # 4. Predict
        if self.model is not None:
            raw_pred = self.model.predict(feats)[0]
            if hasattr(self.model, "predict_proba"):
                probs = self.model.predict_proba(feats)[0]
                class_scores = {c: round(float(p), 4) for c, p in zip(self.model.classes_, probs)}
            else:
                class_scores = {c: (1.0 if c == raw_pred else 0.0) for c in self.classes_}
            pred_class = str(raw_pred)
        else:
            # Rule-based fallback if no model file loaded
            pred_class = "N"
            class_scores = {"N": 1.0, "S": 0.0, "V": 0.0, "F": 0.0, "Q": 0.0}

        latency = (time.perf_counter() - start_t) * 1000.0

        return StructuredECGPrediction(
            patient_id=patient_id,
            window_timestamp_sec=timestamp_sec,
            predicted_class=pred_class,
            class_label_meaning=CLASS_DESCRIPTIONS.get(pred_class, "Cardiac Rhythm Category"),
            class_scores=class_scores,
            # Explicit warning: Random Forest / logistic raw scores are uncalibrated probabilities
            is_calibrated_probability=False,
            signal_quality_status=sqi.status,
            snr_db=sqi.snr_db,
            model_version=self.metadata.get("version", "v1.0.0-baseline"),
            data_provenance=self.metadata.get("dataset", "MIT-BIH Arrhythmia Database"),
            inference_latency_ms=round(latency, 2),
        )
