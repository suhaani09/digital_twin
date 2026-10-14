/**
 * Shared TypeScript types matching the backend schemas exactly.
 */

export interface ModalityFreshness {
  last_timestamp: number;
  age_seconds: number;
  is_fresh: boolean;
  status: 'FRESH' | 'STALE' | 'MISSING';
}

export interface PatientContext {
  patient_id: string;
  age?: number;
  gender?: string;
  medical_history: string[];
  active_medications: string[];
  admission_timestamp?: number | null;
}

export interface HRVMetrics {
  rr_mean_ms: number;
  sdnn_ms: number;
  rmssd_ms: number;
  pnn50: number;
  is_fresh: boolean;
  provenance: string;
}

export interface HemodynamicState {
  heart_rate_bpm: number;
  stroke_volume_ml: number;
  cardiac_output_l_min: number;
  systolic_bp_mmhg: number;
  diastolic_bp_mmhg: number;
  mean_arterial_pressure_mmhg: number;
  pulse_pressure_mmhg: number;
  systemic_vascular_resistance: number;
  compliance_ml_per_mmhg: number;
  is_simulated: boolean;
  model_name: string;
}

export interface ClinicalAlert {
  alert_id: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  title: string;
  description: string;
  evidence: Record<string, any>;
  timestamp: number;
  acknowledged: boolean;
}

export interface RhythmPrediction {
  predicted_class: string;
  class_label_meaning: string;
  class_scores: Record<string, number>;
  is_calibrated_probability: boolean;
  signal_quality_status: string;
  snr_db: number;
  model_version: string;
  inference_latency_ms: number;
}

export interface SignalQuality {
  status: string;
  is_valid: boolean;
  snr_db: number;
  flatline_ratio?: number;
}

export interface DigitalTwinState {
  patient_id: string;
  session_id: string;
  current_time: number;
  is_live_replay: boolean;
  playback_speed: number;
  latest_observations: Record<string, any>;
  modality_freshness: Record<string, ModalityFreshness>;
  ecg_samples: number[];
  ecg_fs: number;
  signal_quality: SignalQuality;
  latest_prediction?: RhythmPrediction | null;
  heart_rate_bpm?: number | null;
  hrv_metrics?: HRVMetrics | null;
  hemodynamics?: HemodynamicState | null;
  blood_glucose_mg_dl?: number | null;
  patient_context: PatientContext;
  clinical_risk_score: {
    news2_score: number;
    risk_category: 'LOW' | 'MEDIUM' | 'HIGH';
    evidence: Record<string, any>;
  };
  active_alerts: ClinicalAlert[];
}

export interface ScenarioDefinition {
  scenario_id: string;
  title: string;
  description: string;
  parameter_overrides: Record<string, number>;
  physiological_hypothesis: string;
  clinical_assumption: string;
}

export interface HemodynamicSummary {
  hr_bpm: number;
  stroke_volume_ml: number;
  cardiac_output_l_min: number;
  systolic_bp_mmhg: number;
  diastolic_bp_mmhg: number;
  mean_arterial_pressure_mmhg: number;
  pulse_pressure_mmhg: number;
  ejection_fraction_pct: number;
  end_diastolic_volume_ml: number;
  end_systolic_volume_ml: number;
  is_stable: boolean;
}

export interface ScenarioComparisonResult {
  scenario_id: string;
  title: string;
  hypothesis: string;
  duration_sec: number;
  changed_parameters: Record<string, { baseline: number; scenario: number }>;
  baseline_summary: HemodynamicSummary;
  scenario_summary: HemodynamicSummary;
  deltas: Record<string, number>;
  sample_trajectories: {
    baseline: Array<{ t: number; p_art: number; p_lv: number; v_lv: number; q_out: number }>;
    scenario: Array<{ t: number; p_art: number; p_lv: number; v_lv: number; q_out: number }>;
  };
  disclaimer: string;
}

export interface SimulationStateResponse {
  sim_time_sec: number;
  v_lv_ml: number;
  p_art_mmhg: number;
  p_ven_mmhg: number;
  params: Record<string, number>;
  cycle_summary: HemodynamicSummary;
}

export interface RawObservationItem {
  patient_id: string;
  session_id: string;
  modality: string;
  timestamp: number;
  values: Record<string, any>;
  unit: string;
  source_type: string;
  provenance: string;
}

