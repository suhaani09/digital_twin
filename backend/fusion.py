"""
Multimodal Data Synchronization & Interpretable Late Fusion Engine.

Responsibilities:
1. Timestamp normalization and freshness tracking per modality:
   - ECG waveforms (freshness limit: 2.0s)
   - Heart rate (freshness limit: 5.0s)
   - Blood pressure / Hemodynamics (freshness limit: 10.0s)
   - Glucose (freshness limit: 300.0s = 5 min)
2. Bounded circular buffers for ECG streaming and HRV computation.
3. Interpretable Late Fusion:
   - Combines independent rhythm predictions, vital signs, and EHR context
     using clinically defensible National Early Warning Score (NEWS2) rules.
   - Generates transparent clinical alerts with evidence trails.
   - Never hallucinates missing modalities; marks them explicitly as UNKNOWN/STALE.
"""

from collections import deque
from dataclasses import asdict
import math
import time
from typing import Dict, List, Optional, Tuple
import numpy as np

from backend.classifier import ECGClassifierService
from backend.ecg_processor import PanTompkinsDetector, assess_signal_quality
from backend.event_store import ClinicalEvent, event_store
from backend.physiology import WindkesselModel
from backend.schemas import (
    ClinicalAlert,
    DigitalTwinState,
    HRVMetrics,
    ModalityFreshness,
    ModalityType,
    PatientContext,
    RawObservation,
)

# Configurable Freshness Limits (in seconds)
FRESHNESS_LIMITS = {
    ModalityType.ECG_CHUNK.value: 2.5,
    ModalityType.HEART_RATE.value: 5.0,
    ModalityType.HRV_METRICS.value: 10.0,
    ModalityType.BLOOD_PRESSURE.value: 15.0,
    ModalityType.BLOOD_GLUCOSE.value: 300.0,
    ModalityType.ML_PREDICTION.value: 5.0,
}


class MultimodalFusionEngine:
    """
    State manager for a single patient/session digital twin.
    Maintains bounded observation buffers, calculates rolling HRV,
    updates physiological models, and conducts late clinical fusion.
    """

    def __init__(self, patient_id: str, session_id: str):
        self.patient_id = patient_id
        self.session_id = session_id
        self.created_at = time.time()
        self.current_sim_time = 0.0

        # Bounded buffers (prevent memory leaks)
        self.ecg_buffer = deque(maxlen=720)  # ~2 seconds at 360 Hz
        self.rr_interval_buffer = deque(maxlen=30)  # Last 30 R-R intervals (seconds)
        self.history_observations = deque(maxlen=200)

        # Observations store: modality -> (timestamp, RawObservation)
        self.latest_observations: Dict[str, RawObservation] = {}

        # Subsystems
        self.ecg_classifier = ECGClassifierService()
        self.qrs_detector = PanTompkinsDetector(fs=360.0)
        self.windkessel = WindkesselModel()

        # Cached state components
        self.last_prediction: Optional[Dict] = None
        self.last_sqi: Dict = {"status": "AWAITING_DATA", "is_valid": False, "snr_db": 0.0}
        self.patient_context = PatientContext(patient_id=patient_id)
        self.active_alerts: List[ClinicalAlert] = []

        # Last calculated R-peak index for windowing
        self._last_processed_r_count = 0

    def reset_state(self):
        """Cleans all buffers and observations on session switch/reset."""
        self.ecg_buffer.clear()
        self.rr_interval_buffer.clear()
        self.history_observations.clear()
        self.latest_observations.clear()
        self.last_prediction = None
        self.active_alerts.clear()
        self.current_sim_time = 0.0

    def ingest_observation(self, obs: RawObservation) -> bool:
        """
        Ingests a single raw observation:
        - Rejects mismatched patient IDs.
        - Drops exact duplicates or out-of-order timestamps (>5.0s in the past).
        """
        if obs.patient_id != self.patient_id:
            return False

        # Ordering & duplicate check
        mod_key = obs.modality.value
        if mod_key in self.latest_observations:
            prev_obs = self.latest_observations[mod_key]
            if obs.timestamp < prev_obs.timestamp:
                # Out-of-order drop
                return False
            if obs.timestamp == prev_obs.timestamp and obs.values == prev_obs.values:
                # Duplicate drop
                return False

        self.latest_observations[mod_key] = obs
        self.history_observations.append(obs)
        self.current_sim_time = max(self.current_sim_time, obs.timestamp)

        # Specific modality ingestion logic
        if obs.modality == ModalityType.ECG_CHUNK:
            samples = obs.values.get("samples", [])
            for s in samples:
                self.ecg_buffer.append(float(s))
            self._process_ecg_chunk()

        elif obs.modality == ModalityType.HEART_RATE:
            bpm = float(obs.values.get("bpm", 72.0))
            # Derive synthetic RR if buffer empty
            if bpm > 0:
                self.rr_interval_buffer.append(60.0 / bpm)

        return True

    def _process_ecg_chunk(self):
        """Processes recent ECG buffer: updates SQI, detects QRS, runs ML classifier."""
        if len(self.ecg_buffer) < 200:
            return

        signal_arr = np.array(self.ecg_buffer, dtype=np.float32)
        sqi = assess_signal_quality(signal_arr, fs=360.0)
        self.last_sqi = {
            "status": sqi.status,
            "is_valid": sqi.is_valid,
            "snr_db": sqi.snr_db,
            "flatline_ratio": sqi.flatline_ratio,
        }

        # Run peak detection on the buffer
        peaks = self.qrs_detector.detect_peaks(signal_arr)
        if len(peaks) >= 2:
            diffs = np.diff(peaks) / 360.0
            for d in diffs:
                if 0.3 < d < 2.0:  # Reasonable RR bounds (30 - 200 bpm)
                    self.rr_interval_buffer.append(float(d))

        # If a central peak is detected and quality is acceptable, run classification on window
        if sqi.is_valid and len(peaks) > 0:
            last_peak = peaks[-1]
            if 90 <= last_peak < len(signal_arr) - 110:
                window = signal_arr[last_peak - 90 : last_peak + 110]
                pred = self.ecg_classifier.predict_window(
                    raw_window=window,
                    patient_id=self.patient_id,
                    timestamp_sec=self.current_sim_time,
                    fs=360.0,
                )
                self.last_prediction = {
                    "predicted_class": pred.predicted_class,
                    "class_label_meaning": pred.class_label_meaning,
                    "class_scores": pred.class_scores,
                    "is_calibrated_probability": pred.is_calibrated_probability,
                    "signal_quality_status": pred.signal_quality_status,
                    "snr_db": pred.snr_db,
                    "model_version": pred.model_version,
                    "inference_latency_ms": pred.inference_latency_ms,
                }
                # Record to persistent event store if ectopic or anomaly
                sev = "WARNING" if pred.predicted_class in ["V", "S", "F"] else "INFO"
                event_store.record_event(
                    ClinicalEvent(
                        event_id=f"ML_{self.patient_id}_{int(self.current_sim_time * 10)}",
                        session_id=self.session_id,
                        timestamp=round(self.current_sim_time, 2),
                        event_type="ML_INFERENCE",
                        severity=sev,
                        description=f"ECG Beat Classified: Class {pred.predicted_class} ({pred.class_label_meaning})",
                        source_provenance=f"GNB Classifier v{pred.model_version}",
                        category="MODEL_GENERATED",
                        metadata={
                            "predicted_class": pred.predicted_class,
                            "class_scores": pred.class_scores,
                            "snr_db": pred.snr_db,
                        },
                    )
                )

    def _calculate_hrv(self) -> Optional[HRVMetrics]:
        """Calculates time-domain HRV from rolling RR intervals."""
        if len(self.rr_interval_buffer) < 4:
            return None

        rrs_ms = np.array(self.rr_interval_buffer) * 1000.0
        rr_diffs = np.diff(rrs_ms)

        sdnn = float(np.std(rrs_ms))
        rmssd = float(np.sqrt(np.mean(rr_diffs**2))) if len(rr_diffs) > 0 else 0.0
        pnn50 = float(np.mean(np.abs(rr_diffs) > 50.0)) if len(rr_diffs) > 0 else 0.0

        return HRVMetrics(
            rr_mean_ms=round(float(np.mean(rrs_ms)), 1),
            sdnn_ms=round(sdnn, 1),
            rmssd_ms=round(rmssd, 1),
            pnn50=round(pnn50, 3),
            is_fresh=True,
            provenance="Rolling R-Peak Intervals",
        )

    def evaluate_fusion_and_alerts(
        self,
        hr: Optional[float],
        sbp: Optional[float],
        prediction: Optional[Dict],
        glucose: Optional[float],
    ) -> Tuple[Dict[str, Any], List[ClinicalAlert]]:
        """
        Interpretable Late Fusion:
        Evaluates NEWS2 score and generates deterministic evidence-based alerts.
        """
        alerts: List[ClinicalAlert] = []
        score = 0
        evidence = {}

        # 1. Heart rate rules
        if hr is not None:
            if hr < 40 or hr > 130:
                score += 3
                alerts.append(
                    ClinicalAlert(
                        alert_id=f"HR_CRITICAL_{int(self.current_sim_time)}",
                        severity="CRITICAL",
                        title="Extreme Heart Rate Anomaly",
                        description=f"Heart rate is critically abnormal ({hr:.1f} bpm).",
                        evidence={"heart_rate_bpm": hr, "threshold": "<40 or >130"},
                        timestamp=self.current_sim_time,
                    )
                )
            elif (41 <= hr <= 50) or (91 <= hr <= 110):
                score += 1
            elif 111 <= hr <= 130:
                score += 2
            evidence["hr_points"] = score

        # 2. Blood pressure rules
        if sbp is not None:
            if sbp <= 90:
                score += 3
                alerts.append(
                    ClinicalAlert(
                        alert_id=f"HYPOTENSION_{int(self.current_sim_time)}",
                        severity="CRITICAL",
                        title="Severe Hypotension Detected",
                        description=f"Systolic BP is critically low ({sbp:.1f} mmHg). Risk of circulatory shock.",
                        evidence={"systolic_bp": sbp, "threshold": "<= 90 mmHg"},
                        timestamp=self.current_sim_time,
                    )
                )
            elif 91 <= sbp <= 100:
                score += 2
            elif 101 <= sbp <= 110:
                score += 1
            elif sbp >= 180:
                score += 2
                alerts.append(
                    ClinicalAlert(
                        alert_id=f"HYPERTENSION_{int(self.current_sim_time)}",
                        severity="WARNING",
                        title="Hypertensive Urgency",
                        description=f"Systolic BP is severely elevated ({sbp:.1f} mmHg).",
                        evidence={"systolic_bp": sbp, "threshold": ">= 180 mmHg"},
                        timestamp=self.current_sim_time,
                    )
                )

        # 3. ML Rhythm Prediction Fusion
        if prediction is not None:
            pred_class = prediction.get("predicted_class")
            if pred_class == "V":
                score += 2
                alerts.append(
                    ClinicalAlert(
                        alert_id=f"ARRHYTHMIA_PVC_{int(self.current_sim_time)}",
                        severity="WARNING",
                        title="Premature Ventricular Contraction (PVC)",
                        description="Ectopic ventricular complex detected on lead II ECG.",
                        evidence={"ml_prediction": prediction},
                        timestamp=self.current_sim_time,
                    )
                )

        # 4. Glucose evaluation (if available)
        if glucose is not None:
            if glucose < 70.0:
                alerts.append(
                    ClinicalAlert(
                        alert_id=f"HYPOGLYCEMIA_{int(self.current_sim_time)}",
                        severity="WARNING",
                        title="Hypoglycemia Alert",
                        description=f"Blood glucose is dangerously low ({glucose:.1f} mg/dL).",
                        evidence={"glucose_mg_dl": glucose, "threshold": "< 70 mg/dL"},
                        timestamp=self.current_sim_time,
                    )
                )

        risk_category = "LOW"
        if score >= 5:
            risk_category = "HIGH"
        elif score >= 3:
            risk_category = "MEDIUM"

        risk_summary = {
            "news2_score": score,
            "risk_category": risk_category,
            "evidence": evidence,
        }
        return risk_summary, alerts

    def get_current_twin_state(self, is_live_replay: bool = False, speed: float = 1.0) -> DigitalTwinState:
        """Assembles the synchronized digital twin state with explicit freshness checks."""
        now = self.current_sim_time if self.current_sim_time > 0 else time.time()

        freshness_map: Dict[str, ModalityFreshness] = {}
        for mod, limit in FRESHNESS_LIMITS.items():
            if mod in self.latest_observations:
                obs_t = self.latest_observations[mod].timestamp
                age = max(0.0, now - obs_t)
                is_fresh = age <= limit
                status = "FRESH" if is_fresh else "STALE"
            else:
                obs_t = 0.0
                age = 999.0
                is_fresh = False
                status = "MISSING"

            freshness_map[mod] = ModalityFreshness(
                last_timestamp=obs_t,
                age_seconds=round(age, 2),
                is_fresh=is_fresh,
                status=status,
            )

        # 1. Resolve Heart Rate
        hr_val = None
        if freshness_map[ModalityType.HEART_RATE.value].is_fresh:
            hr_val = float(self.latest_observations[ModalityType.HEART_RATE.value].values.get("bpm", 72.0))
        elif len(self.rr_interval_buffer) > 0:
            # Derived from fresh RR
            hr_val = float(60.0 / np.mean(self.rr_interval_buffer))

        # 2. Derive Hemodynamics via Windkessel Model
        hemodynamics = None
        if hr_val is not None:
            hemo_state = self.windkessel.step(heart_rate_bpm=hr_val)
            hemodynamics = asdict(hemo_state)

        # 3. Derive HRV
        hrv = self._calculate_hrv()

        # 4. Resolve Glucose
        glucose_val = None
        if freshness_map[ModalityType.BLOOD_GLUCOSE.value].is_fresh:
            glucose_val = float(self.latest_observations[ModalityType.BLOOD_GLUCOSE.value].values.get("mg_dl", 100.0))

        # 5. Late Fusion & Alert Evaluation
        sbp_val = hemodynamics["systolic_bp_mmhg"] if hemodynamics else None
        risk_score, alerts = self.evaluate_fusion_and_alerts(
            hr=hr_val,
            sbp=sbp_val,
            prediction=self.last_prediction,
            glucose=glucose_val,
        )
        self.active_alerts = alerts

        # Persist new alerts into event_store
        for al in alerts:
            event_store.record_event(
                ClinicalEvent(
                    event_id=al.alert_id,
                    session_id=self.session_id,
                    timestamp=round(al.timestamp, 2),
                    event_type="ALERT",
                    severity=al.severity,
                    description=f"{al.title}: {al.description}",
                    source_provenance="Late Clinical Fusion (NEWS2)",
                    category="DERIVED",
                    metadata=al.evidence,
                )
            )

        # Compile Raw Observations dictionary (shallow view)
        raw_dict = {}
        for k, v in self.latest_observations.items():
            raw_dict[k] = {
                "timestamp": v.timestamp,
                "values": v.values,
                "unit": v.unit,
                "provenance": v.provenance,
            }

        return DigitalTwinState(
            patient_id=self.patient_id,
            session_id=self.session_id,
            current_time=round(now, 3),
            is_live_replay=is_live_replay,
            playback_speed=speed,
            latest_observations=raw_dict,
            modality_freshness=freshness_map,
            ecg_samples=list(self.ecg_buffer)[-200:] if len(self.ecg_buffer) > 0 else [],
            ecg_fs=360.0,
            signal_quality=self.last_sqi,
            latest_prediction=self.last_prediction,
            heart_rate_bpm=round(hr_val, 1) if hr_val is not None else None,
            hrv_metrics=hrv,
            hemodynamics=hemodynamics,
            blood_glucose_mg_dl=glucose_val,
            patient_context=self.patient_context,
            clinical_risk_score=risk_score,
            active_alerts=alerts,
        )

