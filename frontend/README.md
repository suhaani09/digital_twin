# PhysioTwin: Multimodal Healthcare Digital Twin Dashboard

An ECG-centered, multimodal healthcare digital twin and clinical simulation system built for research, educational demonstration, and physiological hypothesis testing.

---

## Architecture Overview

```
[MIT-BIH Arrhythmia / Synthetic Fixtures]
              |
              v
     [Replay & Ingestion Service]
              |
              v
   [FastAPI Orchestration & WebSocket Hub] <------- [2-Element Windkessel / ODE Simulation]
              |                                            (backend/physiology.py)
              +-----------------------------+
              |                             |
              v                             v
[2D Doctor Dashboard]         [Future Unity 3D Client]
(React + TypeScript)           (Independent WebSocket Consumer)
```

---

## Getting Started

### 1. Prerequisites
- **Python**: 3.11+
- **Node.js**: v20+ / npm v10+

### 2. Backend Setup
1. Open a terminal in the root directory:
   ```bash
   cd backend
   ```
2. Activate virtual environment:
   * Windows (PowerShell):
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
   * Linux/macOS:
     ```bash
     source .venv/bin/activate
     ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI + WebSocket backend:
   ```bash
   uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   * REST Swagger Documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   * WebSocket Streaming Endpoint: `ws://127.0.0.1:8000/ws`

### 3. Frontend Setup
1. In a separate terminal:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Access the dashboard: [http://localhost:5173](http://localhost:5173)

---

## Dashboard Capabilities

1. **Patient & Session Selector**: Switch between patients (e.g. PhysioNet MIT-BIH `#100`, `#101`, `#106`, etc.) with strict state reset to prevent cross-patient data leakage.
2. **Real-time Replay Controls**: Start, pause, resume, and adjust playback speed ($1\times, 2\times, 5\times$) with live status feedback.
3. **Continuous ECG Oscilloscope**: HTML5 Canvas renderer with clinical millimeter grid ($25\text{ mm/s}, 10\text{ mm/mV}$), zero-phase bandpass filtering ($0.5 - 45\text{ Hz}$), and Signal Quality Index (SQI) monitoring.
4. **AI Rhythm Classifier**: Real-time beat-by-beat AAMI classification (`N`=Normal, `V`=Ventricular ectopic / PVC, `S`=Supraventricular) with uncalibrated Random Forest class scores and inference latency.
5. **Multimodal Freshness Matrix**: Real-time tracking of waveform, HR, HRV, BP, and CGM freshness with configurable tolerance limits. Missing data is tagged `MISSING` rather than hallucinated.
6. **Cardiovascular Hemodynamics**: Live arterial blood pressure, stroke volume, cardiac output, and systemic vascular resistance derived via 2-element Windkessel modeling.
7. **What-If Simulation Experiments**: Execute in-silico scenarios (`exercise`, `beta_blocker`, `vasodilator`, `heart_failure`, `arterial_stiffening`) from identical baseline checkpoints, displaying quantitative comparative tables and parameter deltas.
8. **Clinical Event Timeline**: Real-time audit trail of physiological alerts triggered by interpretable National Early Warning Score (NEWS2) rules.
9. **Explainability & Provenance**: Explicitly delineates between machine-learned pattern classification and deterministic physiological rules.

---

## Running Verification Tests

* Run backend unit and integration tests:
  ```powershell
  python -m pytest backend/tests/test_simulation_engine.py
  python -m pytest backend/tests/test_ecg_pipeline.py
  ```
* Run frontend build & type check:
  ```bash
  cd frontend
  npm run build
  ```
