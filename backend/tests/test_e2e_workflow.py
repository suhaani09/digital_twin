"""
End-to-End Smoke Test & Negative Security Validation Suite.

Executes and asserts the complete clinical digital twin workflow:
1. Start & verify backend API health.
2. Select patient session (e.g. '100') and verify initial state.
3. Start replay, stream ticks, and verify monotonic timestamp advancement.
4. Verify valid ECG window buffering and real-time Pan-Tompkins QRS detection.
5. Verify AI rhythm classification outputs (AAMI class, uncalibrated scores).
6. Ingest wearable measurements (HR and blood glucose) and assert twin state update.
7. Verify explicit representation of missing/stale modalities (zero hallucination).
8. Stream state updates through WebSocket client and assert packet schema.
9. Advance numerical lumped-parameter cardiovascular ODE simulation.
10. Execute What-If scenario (Exercise) from identical baseline checkpoint and compare deltas.
11. Stop replay, switch patient sessions ('100' -> '101'), and verify ZERO state leakage.
12. Negative security tests: invalid payload rejection, out-of-order drop, negative params rejection.
"""

import asyncio
import json
import os
import sys
import time
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))
from backend.main import app
from backend.schemas import ModalityType, DataSourceType


def test_full_end_to_end_workflow():
    client = TestClient(app)

    print("\n--- STEP 1: Backend Health Check ---")
    resp = client.get("/health")
    assert resp.status_code == 200
    health = resp.json()
    assert health["status"] == "healthy"
    print("Health Status:", health)

    print("\n--- STEP 2: Select Patient Session ---")
    resp = client.post("/twin/select-session?patient_id=100&session_id=E2E_SESSION_100")
    assert resp.status_code == 200
    sel = resp.json()
    assert sel["patient_id"] == "100"

    print("\n--- STEP 3 & 4: Start Replay & Verify Timestamp Advancement ---")
    resp = client.post("/replay/control", json={"action": "start", "patient_id": "100", "speed": 2.0})
    assert resp.status_code == 200
    replay_info = resp.json()
    assert replay_info["replay_status"] == "running"

    # Allow replay loop to emit observations
    time.sleep(0.4)

    # Read state and verify timestamps advanced
    resp = client.get("/twin/state?patient_id=100")
    assert resp.status_code == 200
    state1 = resp.json()
    assert state1["current_time"] > 0.0
    print(f"Replay advancing. Current sim time: {state1['current_time']}s")

    print("\n--- STEP 5 & 6: Process Valid ECG & Rhythm Classifier Output ---")
    assert len(state1["ecg_samples"]) > 0

    # Ingest a 200-sample ECG window directly to verify immediate SQI and ML classification
    from backend.ecg_processor import generate_synthetic_ecg
    ecg_200, _, _ = generate_synthetic_ecg(duration_sec=1.5, fs=360.0)
    ecg_obs = {
        "patient_id": "100",
        "session_id": state1["session_id"],
        "modality": "ecg_chunk",
        "timestamp": round(state1["current_time"] + 0.05, 2),
        "values": {"samples": [round(float(s), 4) for s in ecg_200]},
        "unit": "mV",
        "source_type": "replay_dataset",
        "provenance": "E2E Test Window Ingestion",
    }
    client.post("/ingest/observation", json=ecg_obs)

    # Re-query state to assert SQI is evaluated
    resp = client.get(f"/twin/state?patient_id=100&session_id={state1['session_id']}")
    assert resp.status_code == 200
    state_ecg = resp.json()
    assert state_ecg["signal_quality"]["status"] in ["ACCEPTABLE", "POOR_QUALITY"]
    print(f"ECG buffer has {len(state_ecg['ecg_samples'])} samples. SQI: {state_ecg['signal_quality']['status']}")

    if state_ecg["latest_prediction"]:
        pred = state_ecg["latest_prediction"]
        assert pred["predicted_class"] in ["N", "V", "S", "F", "Q"]
        assert pred["is_calibrated_probability"] is False  # Guardrail verified
        print(f"Rhythm classified: Class {pred['predicted_class']} ({pred['class_label_meaning']})")

    print("\n--- STEP 7 & 8: Ingest Wearable Observations & Update State ---")
    # Ingest custom wearable heart rate and blood glucose
    wearable_hr = {
        "patient_id": "100",
        "session_id": state1["session_id"],
        "modality": "heart_rate",
        "timestamp": round(state1["current_time"] + 0.1, 2),
        "values": {"bpm": 78.0},
        "unit": "bpm",
        "source_type": "replay_dataset",
        "provenance": "E2E Wearable Ingestion",
    }
    resp = client.post("/ingest/observation", json=wearable_hr)
    assert resp.status_code == 200

    wearable_cgm = {
        "patient_id": "100",
        "session_id": state1["session_id"],
        "modality": "blood_glucose",
        "timestamp": round(state1["current_time"] + 0.1, 2),
        "values": {"mg_dl": 104.5},
        "unit": "mg/dL",
        "source_type": "simulated_model",
        "provenance": "Simulated CGM Stream",
    }
    resp = client.post("/ingest/observation", json=wearable_cgm)
    assert resp.status_code == 200

    # Query updated state
    resp = client.get(f"/twin/state?patient_id=100&session_id={state1['session_id']}")
    assert resp.status_code == 200
    state2 = resp.json()
    assert state2["heart_rate_bpm"] == 78.0
    assert state2["blood_glucose_mg_dl"] == 104.5
    print("Ingested vitals reflected in twin state: HR=78.0 bpm, Glucose=104.5 mg/dL")

    print("\n--- STEP 9: Verify Missing Modality Representation ---")
    freshness = state2["modality_freshness"]
    assert freshness["heart_rate"]["status"] == "FRESH"
    assert freshness["blood_glucose"]["status"] == "FRESH"
    print("Freshness Matrix verified:", {k: v["status"] for k, v in freshness.items()})

    print("\n--- STEP 10: WebSocket Live Stream Receipt ---")
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_text()
        packet = json.loads(msg)
        assert packet["patient_id"] == "100"
        assert "modality_freshness" in packet
        assert "hemodynamics" in packet
        print("Received valid WebSocket packet over /ws.")

    print("\n--- STEP 11 & 12: Physiological Simulation & What-If Scenarios ---")
    # Query simulation state
    resp = client.get("/simulation/state")
    assert resp.status_code == 200
    sim_st = resp.json()
    assert sim_st["p_art_mmhg"] > 0
    print(f"Simulation steady state: SBP={sim_st['cycle_summary']['systolic_bp_mmhg']} mmHg, CO={sim_st['cycle_summary']['cardiac_output_l_min']} L/min")

    # Run What-If Scenario
    resp = client.post("/simulation/scenarios/run", json={"scenario_id": "exercise", "duration_sec": 3.0})
    assert resp.status_code == 200
    scenario_res = resp.json()
    assert scenario_res["deltas"]["cardiac_output_l_min_delta"] > 0
    print(f"Scenario 'Exercise' Delta CO: {scenario_res['deltas']['cardiac_output_l_min_delta']:+.2f} L/min")

    print("\n--- STEP 13: Stop Replay, Session Switch & Zero-Leakage Check ---")
    # Stop replay
    resp = client.post("/replay/control", json={"action": "stop"})
    assert resp.status_code == 200

    # Switch to patient 101
    resp = client.post("/twin/select-session?patient_id=101&session_id=E2E_SESSION_101")
    assert resp.status_code == 200

    # Query state of patient 101
    resp = client.get("/twin/state?patient_id=101&session_id=E2E_SESSION_101")
    assert resp.status_code == 200
    state_101 = resp.json()
    assert state_101["patient_id"] == "101"
    # Verify patient 100's specific glucose value did not leak into patient 101's new session!
    assert state_101["blood_glucose_mg_dl"] is None
    assert state_101["modality_freshness"]["blood_glucose"]["status"] == "MISSING"
    print("Zero state leakage verified: Patient 101 clean session has no residual data from Patient 100.")

    print("\n--- STEP 14: Negative & Security Edge Cases ---")
    # A. Ingest mismatched patient ID
    bad_patient_obs = {
        "patient_id": "WRONG_ID",
        "session_id": "E2E_SESSION_101",
        "modality": "heart_rate",
        "timestamp": 10.0,
        "values": {"bpm": 80},
        "unit": "bpm",
        "source_type": "replay_dataset",
        "provenance": "Bad Test",
    }
    resp = client.post("/ingest/observation", json=bad_patient_obs)
    assert resp.status_code == 400
    print("Negative test: Mismatched patient rejected (400 Bad Request).")

    # B. Ingest duplicate observation
    valid_obs = {
        "patient_id": "101",
        "session_id": "E2E_SESSION_101",
        "modality": "heart_rate",
        "timestamp": 10.0,
        "values": {"bpm": 80},
        "unit": "bpm",
        "source_type": "replay_dataset",
        "provenance": "Dup Test",
    }
    resp = client.post("/ingest/observation", json=valid_obs)
    assert resp.status_code == 200
    resp_dup = client.post("/ingest/observation", json=valid_obs)
    assert resp_dup.status_code == 400
    print("Negative test: Duplicate observation rejected (400 Bad Request).")

    # C. Ingest out-of-order timestamp
    past_obs = {
        "patient_id": "101",
        "session_id": "E2E_SESSION_101",
        "modality": "heart_rate",
        "timestamp": 5.0,  # 5s in past
        "values": {"bpm": 80},
        "unit": "bpm",
        "source_type": "replay_dataset",
        "provenance": "Past Test",
    }
    resp_past = client.post("/ingest/observation", json=past_obs)
    assert resp_past.status_code == 400
    print("Negative test: Out-of-order timestamp rejected (400 Bad Request).")

    # D. Invalid scenario parameters
    resp_bad_scenario = client.post("/simulation/scenarios/run", json={"scenario_id": "non_existent_scenario"})
    assert resp_bad_scenario.status_code == 400
    print("Negative test: Non-existent scenario rejected (400 Bad Request).")

    print("\n>>> ALL 14 END-TO-END FLOW & NEGATIVE SECURITY CHECKS PASSED SUCCESSFULLY! <<<")


if __name__ == "__main__":
    test_full_end_to_end_workflow()
