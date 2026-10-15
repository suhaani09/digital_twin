# Digital Twin API Reference

## Base URL
Default: `http://localhost:8000`  
WebSocket: `ws://localhost:8000/ws`

---

## 1. ECG & Replay Endpoints

### `GET /ecg/metadata`
Retrieves physical and recording metadata for the currently loaded ECG.

**Query Parameters:**
- `patient_id` (optional, string)
- `session_id` (optional, string)

**Sample Response:**
```json
{
  "patient_id": "100",
  "session_id": "SESSION_DEFAULT",
  "sample_rate_hz": 360.0,
  "total_samples": 21600,
  "total_duration_sec": 60.0,
  "start_timestamp": 1792045200.0,
  "end_timestamp": 1792045260.0,
  "current_time_sec": 14.5,
  "lead_names": ["MLII"],
  "voltage_scale": "mV",
  "status": "running"
}
```

---

### `GET /ecg/window`
Extracts a window of raw calibrated ECG samples centered at a specific timestamp.

**Query Parameters:**
- `center_timestamp_sec` (required, float, default: 0.0)
- `window_sec` (optional, float, default: 2.0, range: [0.5, 10.0])
- `patient_id` (optional, string)
- `session_id` (optional, string)

**Sample Response:**
```json
{
  "patient_id": "100",
  "session_id": "SESSION_DEFAULT",
  "center_timestamp_sec": 14.5,
  "window_sec": 2.0,
  "sample_rate_hz": 360.0,
  "lead_name": "MLII",
  "unit": "mV",
  "timestamps": [13.5, 13.5027, "...", 15.5],
  "samples": [-0.145, -0.150, 0.852, "...", -0.140]
}
```

---

### `POST /replay/control`
Controls replay lifecycle, seeking, and stepping.

**Request Body:**
```json
{
  "action": "start | pause | resume | stop | speed | seek | restart | step_forward | step_backward",
  "speed_multiplier": 1.0,
  "seek_timestamp": 14.5,
  "step_seconds": 2.0
}
```

---

## 2. Evidence Ingestion Endpoints

### `POST /evidence/upload`
Uploads external evidence file (CSV or PDF). Multipart form-data.

**Form Parameters:**
- `file`: UploadFile (CSV or PDF)
- `patient_id` (optional, string)
- `session_id` (optional, string)

**Sample Response (CSV):**
```json
{
  "status": "success",
  "evidence_id": "EVID_a1b2c3d4e5f6_1792045200",
  "filename": "vitals.csv",
  "file_type": "csv",
  "sha256": "8a35e8...514b",
  "observations_ingested": 3,
  "summary": {
    "rows_parsed": 3,
    "modalities_found": ["heart_rate", "blood_glucose", "blood_pressure"],
    "time_range": [10.0, 10.0]
  },
  "diagnostic_disclaimer": "Uploaded evidence parsed for research and digital twin fusion. Non-diagnostic artifact."
}
```

---

### `GET /evidence/list`
Lists all uploaded evidence records for the session.

**Query Parameters:**
- `session_id` (optional, string)

---

## 3. Clinical Events & State Reconstruction

### `GET /events`
Queries chronological events with optional filtering.

**Query Parameters:**
- `session_id` (optional, string)
- `event_type` (optional, string: `ARRHYTHMIA`, `ALERT`, `EVIDENCE_INGESTED`, `REPLAY_CONTROL`, `SCENARIO`)
- `severity` (optional, string: `INFO`, `WARNING`, `CRITICAL`)
- `category` (optional, string)
- `limit` (optional, integer, default: 50)

---

### `GET /twin/state-at`
Reconstructs multi-modal state matrix at a past timestamp without fabricated vitals.

**Query Parameters:**
- `timestamp_sec` (required, float)
- `patient_id` (optional, string)
- `session_id` (optional, string)

**Sample Response:**
```json
{
  "patient_id": "100",
  "session_id": "SESSION_DEFAULT",
  "query_timestamp": 10.0,
  "active_modalities": {
    "heart_rate": { "value": 84.0, "unit": "bpm", "timestamp": 10.0, "source": "CSV Telemetry" },
    "blood_glucose": { "value": 112.5, "unit": "mg/dL", "timestamp": 10.0, "source": "CSV Telemetry" }
  },
  "missing_modalities": ["blood_pressure", "hrv_metrics"],
  "latest_events": ["..."]
}
```

---

## 4. Cardiovascular Simulation Endpoints

- `GET /simulation/state`: Cycle-averaged hemodynamic summary and current ODE state.
- `POST /simulation/control`: Advances or resets the ODE integration clock.
- `GET /simulation/scenarios`: Lists available what-if scenarios (`exercise`, `vasodilation`, `heart_failure`, etc.).
- `POST /simulation/scenarios/run`: Runs baseline vs scenario comparison experiment.

