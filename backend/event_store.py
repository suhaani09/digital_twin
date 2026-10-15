"""
Clinical Event Store and Database Manager.

SQLite-backed persistent event storage and audit log for the Healthcare Digital Twin.
Stores:
- Ingestion events (ECG loaded, wearable evidence uploaded)
- Clinical alerts & rule violations (Hypotension, Tachycardia, PVC detected)
- Model predictions & signal quality changes
- Physiological simulation and what-if scenario runs
- System audit log with provenance tracking
"""

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClinicalEvent(BaseModel):
    event_id: str
    session_id: str
    timestamp: float
    event_type: str = Field(..., description="REPLAY, EVIDENCE_UPLOAD, ML_INFERENCE, ALERT, SCENARIO, SYSTEM")
    severity: str = Field("INFO", description="INFO, WARNING, CRITICAL")
    description: str
    source_provenance: str
    evidence_id: Optional[str] = None
    category: str = Field("OBSERVED", description="OBSERVED, DERIVED, MODEL_GENERATED, SIMULATED")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class EventStore:
    def __init__(self, db_path: str = "data/events.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clinical_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_provenance TEXT NOT NULL,
                    evidence_id TEXT,
                    category TEXT NOT NULL,
                    metadata_json TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_time ON clinical_events (session_id, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON clinical_events (event_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_severity ON clinical_events (severity)")

            # Evidence upload registry table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_registry (
                    evidence_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    upload_timestamp REAL NOT NULL,
                    acquisition_timestamp REAL,
                    source_provenance TEXT NOT NULL,
                    extracted_summary_json TEXT,
                    status TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def record_event(self, event: ClinicalEvent) -> ClinicalEvent:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO clinical_events (
                    event_id, session_id, timestamp, event_type, severity,
                    description, source_provenance, evidence_id, category,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.session_id,
                    event.timestamp,
                    event.event_type,
                    event.severity,
                    event.description,
                    event.source_provenance,
                    event.evidence_id,
                    event.category,
                    json.dumps(event.metadata),
                    event.created_at,
                ),
            )
            conn.commit()
        return event

    def query_events(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        min_timestamp: Optional[float] = None,
        max_timestamp: Optional[float] = None,
        limit: int = 100,
    ) -> List[ClinicalEvent]:
        query = "SELECT * FROM clinical_events WHERE 1=1"
        params: List[Any] = []

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.upper())
        if severity:
            query += " AND severity = ?"
            params.append(severity.upper())
        if category:
            query += " AND category = ?"
            params.append(category.upper())
        if min_timestamp is not None:
            query += " AND timestamp >= ?"
            params.append(min_timestamp)
        if max_timestamp is not None:
            query += " AND timestamp <= ?"
            params.append(max_timestamp)

        query += " ORDER BY timestamp DESC, created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            events: List[ClinicalEvent] = []
            for r in rows:
                meta = {}
                if r["metadata_json"]:
                    try:
                        meta = json.loads(r["metadata_json"])
                    except Exception:
                        pass
                events.append(
                    ClinicalEvent(
                        event_id=r["event_id"],
                        session_id=r["session_id"],
                        timestamp=r["timestamp"],
                        event_type=r["event_type"],
                        severity=r["severity"],
                        description=r["description"],
                        source_provenance=r["source_provenance"],
                        evidence_id=r["evidence_id"],
                        category=r["category"],
                        metadata=meta,
                        created_at=r["created_at"],
                    )
                )
            return events

    def record_evidence(
        self,
        evidence_id: str,
        session_id: str,
        filename: str,
        file_type: str,
        file_hash: str,
        file_size_bytes: int,
        upload_timestamp: float,
        acquisition_timestamp: Optional[float],
        source_provenance: str,
        extracted_summary: Dict[str, Any],
        status: str = "PROCESSED",
    ):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_registry (
                    evidence_id, session_id, filename, file_type, file_hash,
                    file_size_bytes, upload_timestamp, acquisition_timestamp,
                    source_provenance, extracted_summary_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    session_id,
                    filename,
                    file_type,
                    file_hash,
                    file_size_bytes,
                    upload_timestamp,
                    acquisition_timestamp,
                    source_provenance,
                    json.dumps(extracted_summary),
                    status,
                ),
            )
            conn.commit()

    def list_evidence(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM evidence_registry WHERE 1=1"
        params = []
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY upload_timestamp DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                summary = {}
                if r["extracted_summary_json"]:
                    try:
                        summary = json.loads(r["extracted_summary_json"])
                    except Exception:
                        pass
                results.append(
                    {
                        "evidence_id": r["evidence_id"],
                        "session_id": r["session_id"],
                        "filename": r["filename"],
                        "file_type": r["file_type"],
                        "file_hash": r["file_hash"],
                        "file_size_bytes": r["file_size_bytes"],
                        "upload_timestamp": r["upload_timestamp"],
                        "acquisition_timestamp": r["acquisition_timestamp"],
                        "source_provenance": r["source_provenance"],
                        "extracted_summary": summary,
                        "status": r["status"],
                    }
                )
            return results

    def clear_session(self, session_id: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM clinical_events WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM evidence_registry WHERE session_id = ?", (session_id,))
            conn.commit()


# Global event store instance
event_store = EventStore()

