"""
Automated Integration Tests for Real-Time Backend & Data Fusion.

Tests:
1. Timestamp ordering & rejection of backward/stale timestamps.
2. Duplicate observation handling.
3. Freshness limit enforcement (fresh vs stale vs missing).
4. Missing modality behavior (never hallucinating missing glucose or BP).
5. Multiple isolated sessions (ensuring patient data isolation).
6. State reset clears prior patient values.
7. Replay service lifecycle: start -> pause -> resume -> seek -> stop.
8. Windkessel hemodynamic model calculation.
9. Late fusion alert triggering (severe hypotension, tachycardia, arrhythmia).
10. End-to-end WebSocket client receipt of twin state packets.
"""

import asyncio
import time
import pytest
from fastapi.testclient import TestClient

from backend.fusion import MultimodalFusionEngine
from backend.main import app, get_or_create_engine
from backend.physiology import WindkesselModel
from backend.replay_engine import ReplayService, ReplayStatus
from backend.schemas import DataSourceType, ModalityType, RawObservation


@pytest.fixture
def test_engine():
    return MultimodalFusionEngine(patient_id="TEST_PATIENT", session_id="TEST_SESSION")


class TestDataSynchronizationAndFreshness:

    def test_timestamp_ordering_and_duplicate_handling(self, test_engine):
        obs1 = RawObservation(
            patient_id="TEST_PATIENT",
            session_id="TEST_SESSION",
            modality=ModalityType.HEART_RATE,
            timestamp=10.0,
            values={"bpm": 70.0},
            unit="bpm",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        assert test_engine.ingest_observation(obs1) is True

        # Duplicate observation dropped
        assert test_engine.ingest_observation(obs1) is False

        # Out-of-order timestamp dropped
        obs_past = RawObservation(
            patient_id="TEST_PATIENT",
            session_id="TEST_SESSION",
            modality=ModalityType.HEART_RATE,
            timestamp=8.0,
            values={"bpm": 72.0},
            unit="bpm",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        assert test_engine.ingest_observation(obs_past) is False

        # Chronologically subsequent observation accepted
        obs2 = RawObservation(
            patient_id="TEST_PATIENT",
            session_id="TEST_SESSION",
            modality=ModalityType.HEART_RATE,
            timestamp=11.0,
            values={"bpm": 73.0},
            unit="bpm",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        assert test_engine.ingest_observation(obs2) is True

    def test_patient_id_mismatch_rejected(self, test_engine):
        obs_wrong_patient = RawObservation(
            patient_id="DIFFERENT_PATIENT",
            session_id="TEST_SESSION",
            modality=ModalityType.HEART_RATE,
            timestamp=10.0,
            values={"bpm": 80.0},
            unit="bpm",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        assert test_engine.ingest_observation(obs_wrong_patient) is False

    def test_freshness_limits_and_missing_modalities(self, test_engine):
        fresh_eng = MultimodalFusionEngine(patient_id="FRESH_PAT", session_id="FRESH_SESS")
        # Ingest HR at t=10.0
        obs_hr = RawObservation(
            patient_id="FRESH_PAT",
            session_id="FRESH_SESS",
            modality=ModalityType.HEART_RATE,
            timestamp=10.0,
            values={"bpm": 85.0},
            unit="bpm",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        fresh_eng.ingest_observation(obs_hr)

        # Check state at t=10.0 (age = 0s -> FRESH)
        state_fresh = fresh_eng.get_current_twin_state()
        assert state_fresh.modality_freshness["heart_rate"].is_fresh is True
        assert state_fresh.modality_freshness["heart_rate"].status == "FRESH"
        assert state_fresh.heart_rate_bpm == 85.0

        # Blood glucose was never ingested -> MUST BE MISSING, NOT FABRICATED
        assert state_fresh.modality_freshness["blood_glucose"].status == "MISSING"
        assert state_fresh.blood_glucose_mg_dl is None

        # Simulate advance of time by ingesting another observation at t=20.0
        obs_advance = RawObservation(
            patient_id="FRESH_PAT",
            session_id="FRESH_SESS",
            modality=ModalityType.BLOOD_GLUCOSE,
            timestamp=20.0,
            values={"mg_dl": 110.0},
            unit="mg/dL",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        fresh_eng.ingest_observation(obs_advance)

        # HR age is now 20.0 - 10.0 = 10.0s (limit is 5.0s -> STALE)
        state_stale = fresh_eng.get_current_twin_state()
        assert state_stale.modality_freshness["heart_rate"].is_fresh is False
        assert state_stale.modality_freshness["heart_rate"].status == "STALE"


class TestPhysiologyAndLateFusion:

    def test_windkessel_hemodynamic_calculations(self):
        model = WindkesselModel()
        state = model.step(heart_rate_bpm=75.0)

        assert 110.0 <= state.systolic_bp_mmhg <= 135.0
        assert 65.0 <= state.diastolic_bp_mmhg <= 88.0
        assert 4.0 <= state.cardiac_output_l_min <= 6.5
        assert state.pulse_pressure_mmhg == round(state.systolic_bp_mmhg - state.diastolic_bp_mmhg, 1)

    def test_late_fusion_triggers_hypotension_alert(self, test_engine):
        risk, alerts = test_engine.evaluate_fusion_and_alerts(
            hr=72.0,
            sbp=82.0,  # <= 90 mmHg: severe hypotension
            prediction=None,
            glucose=None,
        )
        assert risk["news2_score"] >= 3
        alert_titles = [a.title for a in alerts]
        assert "Severe Hypotension Detected" in alert_titles

    def test_late_fusion_triggers_pvc_arrhythmia_alert(self, test_engine):
        pvc_prediction = {
            "predicted_class": "V",
            "class_label_meaning": "Ventricular ectopic beat",
            "is_calibrated_probability": False,
        }
        risk, alerts = test_engine.evaluate_fusion_and_alerts(
            hr=80.0,
            sbp=120.0,
            prediction=pvc_prediction,
            glucose=None,
        )
        assert risk["news2_score"] >= 2
        alert_titles = [a.title for a in alerts]
        assert "Premature Ventricular Contraction (PVC)" in alert_titles


class TestSessionIsolationAndReset:

    def test_session_isolation(self):
        eng1 = get_or_create_engine("PATIENT_A", "SESS_1")
        eng2 = get_or_create_engine("PATIENT_B", "SESS_2")

        obs_a = RawObservation(
            patient_id="PATIENT_A",
            session_id="SESS_1",
            modality=ModalityType.HEART_RATE,
            timestamp=1.0,
            values={"bpm": 60.0},
            unit="bpm",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        eng1.ingest_observation(obs_a)

        assert eng1.latest_observations["heart_rate"].values["bpm"] == 60.0
        assert "heart_rate" not in eng2.latest_observations

    def test_state_reset_clears_prior_patient_values(self, test_engine):
        obs = RawObservation(
            patient_id="TEST_PATIENT",
            session_id="TEST_SESSION",
            modality=ModalityType.HEART_RATE,
            timestamp=5.0,
            values={"bpm": 95.0},
            unit="bpm",
            source_type=DataSourceType.REPLAY_DATASET,
            provenance="Unit Test",
        )
        test_engine.ingest_observation(obs)
        assert len(test_engine.latest_observations) > 0

        test_engine.reset_state()
        assert len(test_engine.latest_observations) == 0
        assert len(test_engine.ecg_buffer) == 0
        assert len(test_engine.rr_interval_buffer) == 0


class TestFastAPIRoutesAndReplayLifecycle:

    def test_replay_service_lifecycle(self):
        import anyio
        async def _run_lifecycle():
            emitted_obs = []

            def on_obs(obs):
                emitted_obs.append(obs)

            svc = ReplayService(on_observation_cb=on_obs)
            await svc.start(patient_id="100", speed=5.0)
            assert svc.status == ReplayStatus.RUNNING

            # Allow loop to emit 2-3 chunks
            await asyncio.sleep(0.3)
            assert len(emitted_obs) > 0
            assert svc.current_sample_idx > 0

            # Pause
            await svc.pause()
            assert svc.status == ReplayStatus.PAUSED
            idx_paused = svc.current_sample_idx
            await asyncio.sleep(0.15)
            assert svc.current_sample_idx == idx_paused  # No advance while paused

            # Resume
            await svc.resume()
            assert svc.status == ReplayStatus.RUNNING
            await asyncio.sleep(0.15)
            assert svc.current_sample_idx > idx_paused

            # Seek
            svc.seek(timestamp_seconds=2.0)
            assert svc.current_sample_idx == int(2.0 * 360.0)

            # Stop
            await svc.stop()
            assert svc.status == ReplayStatus.STOPPED

        anyio.run(_run_lifecycle)

    def test_rest_endpoints_health_and_ingest(self):
        client = TestClient(app)

        # 1. Health check
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

        # Select session for patient 100
        client.post("/twin/select-session?patient_id=100&session_id=SESSION_DEFAULT")

        # 2. Ingest valid observation
        payload = {
            "patient_id": "100",
            "session_id": "SESSION_DEFAULT",
            "modality": "heart_rate",
            "timestamp": 100.0,
            "values": {"bpm": 76.5},
            "unit": "bpm",
            "source_type": "replay_dataset",
            "provenance": "REST Test",
        }
        resp = client.post("/ingest/observation", json=payload)
        assert resp.status_code == 200

        # 3. Query current state
        resp = client.get("/twin/state?patient_id=100&session_id=SESSION_DEFAULT")
        assert resp.status_code == 200
        state = resp.json()
        assert state["patient_id"] == "100"
        assert state["heart_rate_bpm"] == 76.5
        assert "hemodynamics" in state
        assert state["hemodynamics"]["systolic_bp_mmhg"] > 0

        # 4. Ingest duplicate should fail with 400
        resp = client.post("/ingest/observation", json=payload)
        assert resp.status_code == 400

    def test_websocket_stream_flow(self):
        client = TestClient(app)
        with client.websocket_connect("/ws") as ws:
            packet = ws.receive_json()
            assert "patient_id" in packet
            assert "modality_freshness" in packet
            assert "clinical_risk_score" in packet
