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
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.fusion import MultimodalFusionEngine
from backend.replay_engine import ReplayService, ReplayStatus
from backend.schemas import (
    DigitalTwinState,
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
    engine = get_or_create_engine(obs.patient_id, obs.session_id)
    accepted = engine.ingest_observation(obs)
    if not accepted:
        raise HTTPException(
            status_code=400,
            detail="Observation rejected (mismatched patient, duplicate, or stale timestamp).",
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
    elif action == "pause":
        await replay_service.pause()
    elif action == "resume":
        await replay_service.resume()
    elif action == "stop":
        await replay_service.stop()
    elif action == "seek" and req.seek_seconds is not None:
        replay_service.seek(req.seek_seconds)
    elif action == "speed" and req.speed is not None:
        replay_service.set_speed(req.speed)
    elif action == "reset":
        await replay_service.stop()
        key = f"{current_patient_id}_{current_session_id}"
        if key in active_engines:
            active_engines[key].reset_state()
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    return {
        "action": action,
        "replay_status": replay_service.status.value,
        "patient_id": current_patient_id,
        "session_id": current_session_id,
        "speed": replay_service.speed,
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
        return asdict(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
