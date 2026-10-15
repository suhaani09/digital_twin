"""
Regression and Integration Tests for Major Upgrade:
- Feature 1: Time-Aware ECG Explorer & Window Extraction
- Feature 2: Evidence Ingestion (CSV Telemetry, PDF Document)
- Feature 3: Clinical Event Generation & Persistent SQLite Audit Log
- Feature 4: Timeline & ECG Viewer Synchronization
- Feature 5: Multi-modal Provenance & Evidence-Aware Digital Twin State
"""

import io
import os
import pytest
from fastapi.testclient import TestClient

from backend.main import app, replay_service, get_or_create_engine
from backend.event_store import event_store, ClinicalEvent


@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup clean state for test session
    client = TestClient(app)
    client.post("/twin/select-session?patient_id=100&session_id=SESSION_UPGRADE_TEST")
    yield
    client.post("/twin/reset?patient_id=100&session_id=SESSION_UPGRADE_TEST")


def test_ecg_metadata_and_window_extraction():
    client = TestClient(app)
    
    # 1. Fetch metadata
    meta_resp = client.get("/ecg/metadata")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["fs"] == 360.0
    assert meta["total_samples"] > 0
    assert meta["duration_sec"] > 0
    assert "Lead II" in meta["channel_lead"]

    # 2. Query ECG window at t=2.5s with window_sec=2.0s
    win_resp = client.get("/ecg/window?timestamp=2.5&window_sec=2.0")
    assert win_resp.status_code == 200
    win = win_resp.json()
    assert win["center_timestamp_sec"] == 2.5
    assert win["window_sec"] == 2.0
    assert win["sample_count"] == int(2.0 * 360.0)
    assert len(win["samples"]) == win["sample_count"]
    assert win["start_time_sec"] >= 1.5 - 0.01
    assert win["end_time_sec"] <= 3.5 + 0.01

    # 3. Negative test: window_sec out of bounds
    bad_win = client.get("/ecg/window?timestamp=2.5&window_sec=45.0")
    assert bad_win.status_code == 400


def test_csv_evidence_upload_and_extraction():
    client = TestClient(app)
    
    # Construct a valid multimodal CSV file in memory
    csv_content = """timestamp,modality,value,unit
10.0,heart_rate,84.0,bpm
10.0,blood_glucose,112.5,mg/dL
10.0,blood_pressure,125.0,mmHg
"""
    files = {"file": ("test_vitals.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = client.post(
        "/evidence/upload?patient_id=100&session_id=SESSION_UPGRADE_TEST",
        files=files,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["file_type"] == "CSV"
    assert data["observations_ingested"] == 3

    # Check evidence listing
    list_resp = client.get("/evidence/list?session_id=SESSION_UPGRADE_TEST")
    assert list_resp.status_code == 200
    ev_items = list_resp.json()["evidence"]
    assert len(ev_items) >= 1
    assert ev_items[0]["filename"] == "test_vitals.csv"
    assert "file_hash" in ev_items[0]


def test_pdf_evidence_upload_and_annotation():
    client = TestClient(app)

    # Minimal valid empty PDF structure
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
    )
    files = {"file": ("lab_report.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    resp = client.post(
        "/evidence/upload?patient_id=100&session_id=SESSION_UPGRADE_TEST",
        files=files,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["file_type"] == "PDF"
    assert data["summary"]["evidence_type"] == "CLINICAL_DOCUMENT_PDF"
    assert "clinical_interpretation_disclaimer" in data["summary"]


def test_clinical_events_querying_and_filtering():
    client = TestClient(app)

    # Query events
    evt_resp = client.get("/events?session_id=SESSION_UPGRADE_TEST")
    assert evt_resp.status_code == 200
    evts = evt_resp.json()["events"]
    assert len(evts) >= 1  # Should contain EVIDENCE_UPLOAD from earlier test

    # Filter by event_type
    filtered_resp = client.get("/events?session_id=SESSION_UPGRADE_TEST&event_type=EVIDENCE_UPLOAD")
    assert filtered_resp.status_code == 200
    for e in filtered_resp.json()["events"]:
        assert e["event_type"] == "EVIDENCE_UPLOAD"


def test_replay_lifecycle_and_step_window():
    client = TestClient(app)

    # 1. Start replay
    start_resp = client.post("/replay/control", json={"action": "start", "patient_id": "100", "speed": 2.0})
    assert start_resp.status_code == 200
    assert start_resp.json()["replay_status"] == "running"

    # 2. Step forward
    step_resp = client.post("/replay/control", json={"action": "step_forward"})
    assert step_resp.status_code == 200
    assert step_resp.json()["current_time_sec"] >= 2.0 - 0.05

    # 3. Step backward
    step_back_resp = client.post("/replay/control", json={"action": "step_backward"})
    assert step_back_resp.status_code == 200

    # 4. Restart replay
    restart_resp = client.post("/replay/control", json={"action": "restart"})
    assert restart_resp.status_code == 200
    assert restart_resp.json()["current_time_sec"] == 0.0

    # 5. Stop replay
    stop_resp = client.post("/replay/control", json={"action": "stop"})
    assert stop_resp.status_code == 200
    assert stop_resp.json()["replay_status"] == "stopped"


def test_historical_state_reconstruction_at_timestamp():
    client = TestClient(app)

    # Ingest historical observation at t=5.0s
    obs = {
        "patient_id": "100",
        "session_id": "SESSION_UPGRADE_TEST",
        "modality": "heart_rate",
        "timestamp": 5.0,
        "values": {"bpm": 88.0},
        "unit": "bpm",
        "source_type": "replay_dataset",
        "provenance": "Historical Test",
    }
    client.post("/ingest/observation", json=obs)

    # Query state at t=5.5s
    resp = client.get("/twin/state-at?timestamp=5.5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_historical_reconstruction"] is True
    assert data["heart_rate_bpm"] == 88.0
    assert "ecg_window" in data
    assert data["ecg_window"]["center_timestamp_sec"] == 5.5

