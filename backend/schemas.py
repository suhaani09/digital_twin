"""
Data Models and Schemas for Multimodal Healthcare Digital Twin.

Defines Pydantic models for:
- Ingestion of observations across multiple modalities and sample frequencies.
- Signal quality and calibration status.
- Synchronized Digital Twin state.
- Clinical alerts and evidence.
- Replay control requests.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ModalityType(str, Enum):
    ECG_CHUNK = "ecg_chunk"
    HEART_RATE = "heart_rate"
    HRV_METRICS = "hrv_metrics"
    BLOOD_GLUCOSE = "blood_glucose"
    BLOOD_PRESSURE = "blood_pressure"
    EHR_CONTEXT = "ehr_context"
    ML_PREDICTION = "ml_prediction"
    DEMO_SYNTHETIC = "demo_synthetic"


class DataSourceType(str, Enum):
    PHYSICAL_SENSOR = "physical_sensor"  # Only when real sensor exists!
    REPLAY_DATASET = "replay_dataset"
    SIMULATED_MODEL = "simulated_model"
    MANUAL_INGEST = "manual_ingest"


class RawObservation(BaseModel):
    patient_id: str
    session_id: str
    modality: ModalityType
    timestamp: float = Field(..., description="UNIX epoch seconds or monotonic simulation seconds")
    values: Dict[str, Any] = Field(..., description="Measurement dictionary, e.g. {'bpm': 74.2}")
    unit: str
    source_type: DataSourceType = DataSourceType.REPLAY_DATASET
    provenance: str = Field(..., description="e.g. 'MIT-BIH Record 100' or 'Simulated Windkessel'")


class PatientContext(BaseModel):
    patient_id: str
    age: Optional[int] = 58
    gender: Optional[str] = "M"
    medical_history: List[str] = Field(default_factory=lambda: ["Hypertension", "History of CAD"])
    active_medications: List[str] = Field(default_factory=lambda: ["Metoprolol 50mg", "Aspirin 81mg"])
    admission_timestamp: Optional[float] = None


class HRVMetrics(BaseModel):
    rr_mean_ms: float
    sdnn_ms: float
    rmssd_ms: float
    pnn50: float
    is_fresh: bool = True
    provenance: str = "Derived R-peaks"


class ClinicalAlert(BaseModel):
    alert_id: str
    severity: str = Field(..., description="INFO, WARNING, or CRITICAL")
    title: str
    description: str
    evidence: Dict[str, Any]
    timestamp: float
    acknowledged: bool = False


class ModalityFreshness(BaseModel):
    last_timestamp: float
    age_seconds: float
    is_fresh: bool
    status: str = "FRESH"


class DigitalTwinState(BaseModel):
    patient_id: str
    session_id: str
    current_time: float
    is_live_replay: bool
    playback_speed: float

    # Raw / Latest Ingested Observations
    latest_observations: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    modality_freshness: Dict[str, ModalityFreshness] = Field(default_factory=dict)

    # Signal & Rhythm Analytics
    ecg_samples: List[float] = Field(default_factory=list, description="Recent 1-2 sec scrolling buffer")
    ecg_fs: float = 360.0
    signal_quality: Dict[str, Any] = Field(default_factory=dict)
    latest_prediction: Optional[Dict[str, Any]] = None

    # Vitals & Physiological Model Output
    heart_rate_bpm: Optional[float] = None
    hrv_metrics: Optional[HRVMetrics] = None
    hemodynamics: Optional[Dict[str, Any]] = None
    blood_glucose_mg_dl: Optional[float] = None

    # Patient EHR Context
    patient_context: PatientContext

    # Clinical Decisions & Alerts (Late Fusion)
    clinical_risk_score: Dict[str, Any] = Field(default_factory=dict)
    active_alerts: List[ClinicalAlert] = Field(default_factory=list)


class ReplayControlRequest(BaseModel):
    action: str = Field(..., description="start, pause, resume, stop, reset, seek")
    patient_id: Optional[str] = "100"
    speed: Optional[float] = 1.0
    seek_seconds: Optional[float] = None


class SimulationControlRequest(BaseModel):
    action: str = Field(..., description="advance, reset, pause, resume, set_params")
    advance_seconds: Optional[float] = 1.0
    hr_bpm: Optional[float] = None
    e_max: Optional[float] = None
    r_per: Optional[float] = None
    c_art: Optional[float] = None


class ScenarioRunRequest(BaseModel):
    scenario_id: Optional[str] = "exercise"
    title: Optional[str] = None
    description: Optional[str] = None
    parameter_overrides: Optional[Dict[str, float]] = None
    duration_sec: float = 6.0


