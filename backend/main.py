"""
FastAPI Server & WebSocket Orchestrator for Healthcare Digital Twin.

Provides endpoints for:
- Health check
- Ingestion of multimodal observations
- Session management & state querying
- Historical observation timelines
- Replay control (start, pause, resume, stop, speed, seek)
- Real-time WebSocket broadcasting with connection tracking
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware

import numpy as np
from backend.event_store import ClinicalEvent, event_store
from backend.evidence_ingestion import evidence_service
from backend.fusion import MultimodalFusionEngine
from backend.replay_engine import ReplayService, ReplayStatus
from backend.schemas import (
    DigitalTwinState,
    ModalityType,
    PatientContext,
    RawObservation,
    ReplayControlRequest,
)

# Global Session & Orchestration Store
active_engines: Dict[str, MultimodalFusionEngine] = {}
current_patient_id = "100"
current_session_id = "SESSION_DEFAULT"
connected_websockets: List[WebSocket] = []


def get_or_create_engine(patient_id: str, session_id: str) -> MultimodalFusionEngine:
    global active_engines
    key = f"{patient_id}_{session_id}"
    if key not in active_engines:
        active_engines[key] = MultimodalFusionEngine(patient_id=patient_id, session_id=session_id)
    return active_engines[key]


def on_replay_observation(obs: RawObservation):
    """Callback fired by the ReplayService whenever a new observation is emitted."""
    engine = get_or_create_engine(obs.patient_id, obs.session_id)
    engine.ingest_observation(obs)


# Instantiate Replay Service
replay_service = ReplayService(on_observation_cb=on_replay_observation)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize default engine
    get_or_create_engine(current_patient_id, current_session_id)
    yield
    # Cleanup on shutdown
    await replay_service.stop()


app = FastAPI(
    title="Multimodal Healthcare Digital Twin API",
    description="Real-time ECG processing, late fusion, and physiological modeling backend.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Healthcare Digital Twin Backend",
        "active_sessions": list(active_engines.keys()),
        "current_patient": current_patient_id,
        "replay_status": replay_service.status.value,
        "ws_clients": len(connected_websockets),
    }


@app.get("/twin/state", response_model=DigitalTwinState)
def get_twin_state(patient_id: Optional[str] = None, session_id: Optional[str] = None):
    p_id = patient_id or current_patient_id
    s_id = session_id or current_session_id
    engine = get_or_create_engine(p_id, s_id)
    return engine.get_current_twin_state(
        is_live_replay=(replay_service.status == ReplayStatus.RUNNING),
        speed=replay_service.speed,
    )


@app.post("/twin/select-session")
def select_session(patient_id: str, session_id: str = "SESSION_1"):
    global current_patient_id, current_session_id
    current_patient_id = patient_id
    current_session_id = session_id
    engine = get_or_create_engine(patient_id, session_id)
    return {
        "message": f"Selected patient {patient_id} with session {session_id}",
        "patient_id": patient_id,
        "session_id": session_id,
    }


@app.post("/twin/reset")
async def reset_twin(patient_id: Optional[str] = None, session_id: Optional[str] = None):
    p_id = patient_id or current_patient_id
    s_id = session_id or current_session_id
    await replay_service.stop()
    key = f"{p_id}_{s_id}"
    if key in active_engines:
        active_engines[key].reset_state()
    return {"message": f"Twin state reset for {p_id}_{s_id}"}


@app.post("/ingest/observation")
def ingest_observation(obs: RawObservation):
    if obs.patient_id != current_patient_id:
        raise HTTPException(
            status_code=400,
            detail=f"Mismatched patient ID: current session is '{current_patient_id}', but observation has '{obs.patient_id}'.",
        )
    engine = get_or_create_engine(obs.patient_id, obs.session_id)
    accepted = engine.ingest_observation(obs)
    if not accepted:
        raise HTTPException(
            status_code=400,
            detail="Observation rejected (duplicate or stale timestamp).",
        )
    return {"status": "accepted", "modality": obs.modality, "timestamp": obs.timestamp}



@app.get("/twin/history")
def get_history(patient_id: Optional[str] = None, session_id: Optional[str] = None):
    p_id = patient_id or current_patient_id
    s_id = session_id or current_session_id
    engine = get_or_create_engine(p_id, s_id)
    return {
        "patient_id": p_id,
        "count": len(engine.history_observations),
        "history": list(engine.history_observations),
    }


@app.get("/twin/alerts")
def get_alerts(patient_id: Optional[str] = None, session_id: Optional[str] = None):
    p_id = patient_id or current_patient_id
    s_id = session_id or current_session_id
    engine = get_or_create_engine(p_id, s_id)
    return {"patient_id": p_id, "alerts": engine.active_alerts}


@app.post("/replay/control")
async def control_replay(req: ReplayControlRequest):
    global current_patient_id, current_session_id
    action = req.action.lower()
    p_id = req.patient_id or current_patient_id

    if action == "start":
        current_patient_id = p_id
        current_session_id = f"REPLAY_{p_id}_{int(time.time())}"
        engine = get_or_create_engine(current_patient_id, current_session_id)
        engine.reset_state()
        await replay_service.start(
            patient_id=p_id,
            session_id=current_session_id,
            speed=req.speed or 1.0,
        )
        event_store.record_event(
            ClinicalEvent(
                event_id=f"REPLAY_START_{int(time.time()*1000)}",
                session_id=current_session_id,
                timestamp=0.0,
                event_type="REPLAY",
                severity="INFO",
                description=f"ECG Replay started for Patient {p_id} at {req.speed or 1.0}x speed.",
                source_provenance=f"MIT-BIH Record {p_id}",
                category="OBSERVED",
            )
        )
    elif action == "restart":
        replay_service.seek(0.0)
        engine = get_or_create_engine(current_patient_id, current_session_id)
        engine.reset_state()
        await replay_service.resume()
        event_store.record_event(
            ClinicalEvent(
                event_id=f"REPLAY_RESTART_{int(time.time()*1000)}",
                session_id=current_session_id,
                timestamp=0.0,
                event_type="REPLAY",
                severity="INFO",
                description="ECG Replay restarted from t=0.0s.",
                source_provenance=f"MIT-BIH Record {current_patient_id}",
                category="OBSERVED",
            )
        )
    elif action == "pause":
        await replay_service.pause()
    elif action == "resume":
        await replay_service.resume()
    elif action == "stop":
        await replay_service.stop()
        event_store.record_event(
            ClinicalEvent(
                event_id=f"REPLAY_STOP_{int(time.time()*1000)}",
                session_id=current_session_id,
                timestamp=round(replay_service.current_sample_idx / replay_service.fs if replay_service.fs else 0.0, 2),
                event_type="REPLAY",
                severity="INFO",
                description="ECG Replay stopped.",
                source_provenance=f"MIT-BIH Record {current_patient_id}",
                category="OBSERVED",
            )
        )
    elif action == "seek" and req.seek_seconds is not None:
        replay_service.seek(req.seek_seconds)
    elif action == "step_forward":
        replay_service.step_window(window_sec=2.0, forward=True)
    elif action == "step_backward":
        replay_service.step_window(window_sec=2.0, forward=False)
    elif action == "speed" and req.speed is not None:
        replay_service.set_speed(req.speed)
    elif action == "reset":
        await replay_service.stop()
        key = f"{current_patient_id}_{current_session_id}"
        if key in active_engines:
            active_engines[key].reset_state()
        event_store.clear_session(current_session_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    return {
        "action": action,
        "replay_status": replay_service.status.value,
        "patient_id": current_patient_id,
        "session_id": current_session_id,
        "speed": replay_service.speed,
        "current_time_sec": round(replay_service.current_sample_idx / replay_service.fs if replay_service.fs else 0.0, 3),
    }


# =====================================================================
# Physiological Simulation & What-If Experiment Endpoints
# =====================================================================

from backend.physiology import CardiovascularModel, CardiovascularParams
from backend.scenarios import ScenarioManager
from backend.schemas import ScenarioRunRequest, SimulationControlRequest

# Independent global simulation engine and scenario manager
simulation_engine = CardiovascularModel()
scenario_manager = ScenarioManager(base_model=simulation_engine)


@app.get("/simulation/state")
def get_simulation_state():
    """Returns the current state and cycle-averaged hemodynamic biomarkers of the simulation engine."""
    summary = simulation_engine.summarize_hemodynamics()
    return {
        "sim_time_sec": round(simulation_engine.sim_time, 4),
        "v_lv_ml": round(simulation_engine.v_lv, 2),
        "p_art_mmhg": round(simulation_engine.p_art, 2),
        "p_ven_mmhg": round(simulation_engine.p_ven, 2),
        "params": asdict(simulation_engine.params),
        "cycle_summary": asdict(summary),
    }


@app.post("/simulation/control")
async def control_simulation(req: SimulationControlRequest):
    """
    Advances or resets the separate physiological cardiovascular simulation clock.
    Does not block the async event loop during numerical integration.
    """
    action = req.action.lower()

    if action == "advance":
        sec = req.advance_seconds or 1.0
        # Run numerical integration in thread pool to prevent blocking WebSocket loop
        await asyncio.to_thread(simulation_engine.run_simulation, duration_sec=sec, record_history=True)
    elif action == "reset":
        simulation_engine.reset()
    elif action == "set_params":
        if req.hr_bpm is not None:
            simulation_engine.params.hr_bpm = req.hr_bpm
        if req.e_max is not None:
            simulation_engine.params.e_max = req.e_max
        if req.r_per is not None:
            simulation_engine.params.r_per = req.r_per
        if req.c_art is not None:
            simulation_engine.params.c_art = req.c_art
        simulation_engine.params.validate()
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported simulation action: {action}")

    summary = simulation_engine.summarize_hemodynamics()
    return {
        "action": action,
        "sim_time_sec": round(simulation_engine.sim_time, 4),
        "summary": asdict(summary),
    }


@app.get("/simulation/scenarios")
def list_preset_scenarios():
    """Lists pre-configured what-if physiological scenarios."""
    return {"scenarios": scenario_manager.get_preset_scenarios()}


@app.post("/simulation/scenarios/run")
async def run_scenario_experiment(req: ScenarioRunRequest):
    """
    Executes a reproducible what-if experiment comparing a steady-state baseline
    against an intervention scenario from identical initial conditions.
    """
    try:
        if req.parameter_overrides:
            scenario_input = {
                "scenario_id": req.scenario_id or "custom_intervention",
                "title": req.title or "Custom What-If Intervention",
                "description": req.description or "User-defined parameter modification experiment",
                "parameter_overrides": req.parameter_overrides,
                "physiological_hypothesis": "Evaluation of parametric perturbation on hemodynamics.",
                "clinical_assumption": "Hypothetical in-silico simulation model assumption.",
            }
        else:
            scenario_input = req.scenario_id

        # Run CPU-bound ODE simulation in threadpool
        result = await asyncio.to_thread(
            scenario_manager.run_experiment,
            scenario_input=scenario_input,
            duration_sec=req.duration_sec,
        )
        # Record scenario execution event
        engine = get_or_create_engine(current_patient_id, current_session_id)
        scen_id = result.scenario_id
        delta_co = result.deltas.get("cardiac_output_l_min", 0.0) if result.deltas else 0.0
        event_store.record_event(
            ClinicalEvent(
                event_id=f"SCENARIO_{scen_id}_{int(time.time()*1000)}",
                session_id=current_session_id,
                timestamp=round(engine.current_sim_time, 2),
                event_type="SCENARIO",
                severity="INFO",
                description=f"What-If Scenario '{result.title}' executed (Delta CO: {delta_co:+.2f} L/min).",
                source_provenance="Cardiovascular ODE Engine",
                category="SIMULATED",
                metadata={
                    "scenario_id": scen_id,
                    "deltas": result.deltas,
                    "baseline_summary": result.baseline_summary,
                },
            )
        )
        return asdict(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =====================================================================
# ECG Recording Explorer & Time-Aware Inspection Endpoints
# =====================================================================

@app.get("/ecg/metadata")
def get_ecg_metadata():
    """Returns timing, frequency, sample count, and duration of active recording."""
    return replay_service.get_metadata()


@app.get("/ecg/window")
def get_ecg_window(
    timestamp: float = Query(..., description="Target center timestamp in seconds"),
    window_sec: float = Query(2.0, description="Window size in seconds (e.g. 1.0 to 10.0)"),
):
    """
    Returns windowed ECG samples centered around the requested timestamp.
    Does not mutate or interrupt active playback replay.
    """
    if window_sec < 0.2 or window_sec > 30.0:
        raise HTTPException(status_code=400, detail="window_sec must be between 0.2 and 30.0 seconds")
    return replay_service.get_window(center_timestamp_sec=timestamp, window_sec=window_sec)


# =====================================================================
# Clinical Evidence Ingestion Endpoints (CSV, PDF, Telemetry)
# =====================================================================

@app.post("/evidence/upload")
async def upload_evidence(
    file: UploadFile = File(...),
    patient_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """
    Secure evidence upload endpoint. Supports CSV (ECG, vitals) and PDF clinical reports.
    Computes cryptographic SHA-256 hash, parses content, and records to Event Store.
    """
    p_id = patient_id or current_patient_id
    s_id = session_id or current_session_id
    engine = get_or_create_engine(p_id, s_id)

    filename = file.filename or "unknown_file"
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds maximum 25 MB limit.")

    ext = filename.split(".")[-1].lower() if "." in filename else ""

    try:
        if ext == "csv":
            summary, observations = evidence_service.process_csv_evidence(
                file_bytes=file_bytes,
                filename=filename,
                session_id=s_id,
                patient_id=p_id,
            )
            # Ingest extracted observations into digital twin engine
            for obs in observations:
                engine.ingest_observation(obs)
                # If custom ECG was uploaded, load into replay service
                if obs.modality == ModalityType.ECG_CHUNK and "samples" in obs.values:
                    samples_arr = np.array(obs.values["samples"], dtype=np.float32)
                    fs_val = float(obs.values.get("fs", 360.0))
                    replay_service.load_custom_signal(
                        signal_array=samples_arr,
                        fs=fs_val,
                        patient_id=p_id,
                        session_id=s_id,
                        provenance=f"Uploaded CSV ({filename})",
                    )

            return {
                "status": "success",
                "filename": filename,
                "file_type": "CSV",
                "summary": summary,
                "observations_ingested": len(observations),
            }

        elif ext == "pdf":
            summary, _ = evidence_service.process_pdf_evidence(
                file_bytes=file_bytes,
                filename=filename,
                session_id=s_id,
                patient_id=p_id,
            )
            return {
                "status": "success",
                "filename": filename,
                "file_type": "PDF",
                "summary": summary,
                "observations_ingested": 0,
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '.{ext}'. Supported types: .csv (ECG/vitals), .pdf (documents).",
            )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@app.get("/evidence/list")
def list_evidence(session_id: Optional[str] = None):
    """Lists registered evidence items with SHA-256 hashes and extraction summaries."""
    s_id = session_id or current_session_id
    return {"session_id": s_id, "evidence": event_store.list_evidence(s_id)}


# =====================================================================
# Clinical Event Timeline & Audit Log Endpoints
# =====================================================================

@app.get("/events")
def get_clinical_events(
    session_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    min_timestamp: Optional[float] = None,
    max_timestamp: Optional[float] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """
    Returns filtered clinical events and audit logs from persistent SQLite store.
    """
    s_id = session_id or current_session_id
    events = event_store.query_events(
        session_id=s_id,
        event_type=event_type,
        severity=severity,
        category=category,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        limit=limit,
    )
    return {
        "session_id": s_id,
        "count": len(events),
        "events": [e.model_dump() for e in events],
    }


@app.get("/twin/state-at")
def get_state_at_timestamp(timestamp: float = Query(..., description="Target historical timestamp in seconds")):
    """
    Reconstructs the twin's observable state at the requested timestamp.
    Does not leak future observations.
    """
    engine = get_or_create_engine(current_patient_id, current_session_id)
    # Find matching observations up to target timestamp
    past_obs = [o for o in engine.history_observations if o.timestamp <= timestamp]
    ecg_window = replay_service.get_window(center_timestamp_sec=timestamp, window_sec=2.0)

    # Reconstruct last known vitals at or before target timestamp
    last_hr = next((o.values.get("bpm") for o in reversed(past_obs) if o.modality.value == "heart_rate"), None)
    last_glu = next((o.values.get("mg_dl") for o in reversed(past_obs) if o.modality.value == "blood_glucose"), None)

    return {
        "timestamp": timestamp,
        "patient_id": current_patient_id,
        "session_id": current_session_id,
        "is_historical_reconstruction": True,
        "ecg_window": ecg_window,
        "heart_rate_bpm": last_hr,
        "blood_glucose_mg_dl": last_glu,
        "observations_count_up_to_time": len(past_obs),
    }


@app.websocket("/ws")
async def websocket_stream(websocket: WebSocket):
    """
    High-performance real-time WebSocket state streaming endpoint.
    Emits synchronized DigitalTwinState packets at ~10 Hz (every 100ms).
    """
    await websocket.accept()
    connected_websockets.append(websocket)
    print("WebSocket client connected. Total clients:", len(connected_websockets))

    try:
        while True:
            engine = get_or_create_engine(current_patient_id, current_session_id)
            state = engine.get_current_twin_state(
                is_live_replay=(replay_service.status == ReplayStatus.RUNNING),
                speed=replay_service.speed,
            )
            # Broadcast state
            await websocket.send_text(state.model_dump_json())
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        print("WebSocket client disconnected.")
    except Exception as e:
        print("WebSocket streaming error:", e)
    finally:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)
