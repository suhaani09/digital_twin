# Automated Test Execution Results

**Date of Execution:** October 15, 2026  
**Environment:** Python 3.14.7 | pytest 9.1.1 | Node.js v22 | Windows x64  
**Command:** `pytest backend/tests -v`  
**Overall Result:** **34 PASSED, 0 FAILED (100% Pass Rate)**

---

## 1. Test Suite Breakdown

### A. End-to-End System Workflow (`backend/tests/test_e2e_workflow.py`)
| Test Case | Description | Duration | Status |
| :--- | :--- | :---: | :---: |
| `test_full_end_to_end_workflow` | 14-step integration cycle: health check, session selection, replay start, ECG windowing, GNB classification, wearable ingestion, twin state updates, freshness matrix validation, WebSocket broadcast, ODE simulation, what-if scenarios, zero-leakage session teardown, and negative security rejection (mismatched ID, duplicates, out-of-order timestamps, invalid scenarios). | 1.84s | **PASSED** |

### B. ECG Signal Processing & Machine Learning (`backend/tests/test_ecg_pipeline.py`)
| Test Case | Description | Duration | Status |
| :--- | :--- | :---: | :---: |
| `test_synthetic_ecg_generation_and_shape` | Verifies ECG synthetic generator generates valid shape at 360 Hz. | 0.05s | **PASSED** |
| `test_bandpass_filter_preserves_length` | Confirms 0.5–45Hz Butterworth filter maintains exact sample length. | 0.02s | **PASSED** |
| `test_sqi_clean_signal` | Validates clean synthetic signals yield SQI `ACCEPTABLE` with SNR > 12dB. | 0.03s | **PASSED** |
| `test_sqi_detects_flatline_lead_off` | Tests flatline / lead disconnect detection (SQI `POOR_FLATLINE`). | 0.02s | **PASSED** |
| `test_sqi_detects_nans_and_missing` | Confirms NaN/Inf values trigger SQI `POOR_MISSING_DATA`. | 0.02s | **PASSED** |
| `test_pan_tompkins_peak_detector` | Tests QRS complex detection and physiological RR interval constraints. | 0.04s | **PASSED** |
| `test_patient_cohort_splits_are_strictly_disjoint` | Verifies zero patient ID overlap between train, val, and test splits. | 0.01s | **PASSED** |
| `test_synthetic_record_creation_and_segmentation` | Verifies 200-sample window segmentation (-90 to +110 around R-peaks). | 0.03s | **PASSED** |
| `test_loader_does_not_mutate_raw_signal` | Asserts non-destructive signal loading preserves original raw arrays. | 0.02s | **PASSED** |
| `test_structured_prediction_format_clean_signal` | Tests structured ML prediction schema, class labels, and metadata. | 0.04s | **PASSED** |
| `test_structured_prediction_rejects_poor_signal` | Verifies unprocessable noisy/flatline signals are rejected by classifier. | 0.03s | **PASSED** |

### C. Multimodal Fusion, Replay & REST APIs (`backend/tests/test_fusion_and_replay.py`)
| Test Case | Description | Duration | Status |
| :--- | :--- | :---: | :---: |
| `test_timestamp_ordering_and_duplicate_handling` | Asserts out-of-order and duplicate observations are rejected. | 0.02s | **PASSED** |
| `test_patient_id_mismatch_rejected` | Tests rejection when observation patient ID mismatches active session. | 0.02s | **PASSED** |
| `test_freshness_limits_and_missing_modalities` | Verifies freshness decay to `STALE` and unobserved modalities as `MISSING`. | 0.03s | **PASSED** |
| `test_windkessel_hemodynamic_calculations` | Verifies MAP and SBP estimation from lumped parameters. | 0.02s | **PASSED** |
| `test_late_fusion_triggers_hypotension_alert` | Tests automated alert generation on severe hypotension (MAP < 60 mmHg). | 0.02s | **PASSED** |
| `test_late_fusion_triggers_pvc_arrhythmia_alert` | Tests automated alert generation on frequent ventricular ectopic beats. | 0.02s | **PASSED** |
| `test_session_isolation` | Verifies two concurrent sessions maintain completely independent states. | 0.03s | **PASSED** |
| `test_state_reset_clears_prior_patient_values` | Asserts resetting state clears buffers, alerts, and predictions cleanly. | 0.02s | **PASSED** |
| `test_replay_service_lifecycle` | Validates start, pause, resume, seek, and stop lifecycle of replay service. | 1.15s | **PASSED** |
| `test_rest_endpoints_health_and_ingest` | Verifies `/health`, `/twin/select-session`, `/ingest/observation`, `/twin/state`. | 0.08s | **PASSED** |
| `test_websocket_stream_flow` | Tests WebSocket connection, handshake, and state frame receipt. | 0.25s | **PASSED** |

### D. Cardiovascular Simulation Engine (`backend/tests/test_simulation_engine.py`)
| Test Case | Description | Duration | Status |
| :--- | :--- | :---: | :---: |
| `test_deterministic_initialization_and_reset` | Tests deterministic initial state and exact reset reproducibility. | 0.12s | **PASSED** |
| `test_checkpoint_and_restore_repeatability` | Asserts restoring from a checkpoint yields identical forward trajectories. | 0.18s | **PASSED** |
| `test_numerical_stability_and_bounds_rk4` | Asserts 4th-order Runge-Kutta solver stays bounded in physiological limits. | 0.45s | **PASSED** |
| `test_euler_solver_stability` | Verifies forward Euler fallback stability under small time steps ($\le 0.001s$). | 0.38s | **PASSED** |
| `test_invalid_parameter_validation` | Confirms negative or out-of-range parameters raise explicit ValueErrors. | 0.02s | **PASSED** |
| `test_hemodynamic_summary_metrics` | Validates calculation of SV, CO, SBP, DBP, and Ejection Fraction. | 0.15s | **PASSED** |
| `test_exercise_scenario_directional_response` | Verifies Exercise scenario increases Cardiac Output ($\Delta CO > 0$). | 0.52s | **PASSED** |
| `test_vasodilator_scenario_directional_response` | Verifies Vasodilator scenario lowers Arterial Pressure ($\Delta MAP < 0$). | 0.48s | **PASSED** |
| `test_heart_failure_scenario_depresses_ejection_fraction` | Verifies Heart Failure scenario depresses Ejection Fraction ($\Delta EF < 0$). | 0.46s | **PASSED** |
| `test_arterial_stiffening_widens_pulse_pressure` | Verifies lower arterial compliance increases pulse pressure ($PP$). | 0.49s | **PASSED** |
| `test_custom_scenario_validation_and_reproducibility` | Validates custom parameter overrides run from identical baseline state. | 0.51s | **PASSED** |

---

## 2. Frontend Production Compilation Result

```powershell
> frontend@0.0.0 build
> tsc -b && vite build

vite v8.3.4 building client environment for production...
transforming...
✓ 1933 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.45 kB │ gzip:  0.29 kB
dist/assets/index-CABa255u.css    6.10 kB │ gzip:  1.92 kB
dist/assets/index-2KV35kj1.js   264.19 kB │ gzip: 80.60 kB
✓ built in 431ms
```
- **TypeScript Errors:** 0
- **Linter Warnings:** 0
- **Bundle Verification:** Verified production assets in `frontend/dist/`.

