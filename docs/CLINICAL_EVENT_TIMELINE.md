# Clinical Event Timeline & Audit Log Architecture

## 1. Overview and Design Principles

The Clinical Event Timeline provides a unified, persistent ledger of all physiological transitions, algorithmic detections, data ingestion operations, what-if scenario simulations, and operator interventions.

The store is persisted in SQLite (`data/events.db`) using strict parameterized queries to prevent SQL injection and ensure durable chronological tracking across application restarts.

```
+------------------------------------------------------------------------------------+
|                         CLINICAL EVENT & AUDIT LOG STORE                           |
+------------------------------------------------------------------------------------+
|  Event Ingestion Sources:                                                         |
|  - ECG ML Classifier (Rhythm Arrhythmia Detections: PVC, PAC, etc.)                |
|  - Late Fusion Rules (Hypotension, Tachycardia, Multi-modal Alerts)                 |
|  - Evidence Ingestion (CSV / PDF Evidence Ingested with SHA-256 Hashes)           |
|  - Operator Replay Controls (Start, Pause, Resume, Seek, Restart, Step)            |
|  - Cardiovascular ODE Simulation (Scenario Run: Exercise, Hemorrhage, etc.)        |
+------------------------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------------------------+
|  SQLite Storage Engine: `data/events.db` (`clinical_events` table)                 |
|  * Indexed by: (session_id, timestamp DESC)                                        |
+------------------------------------------------------------------------------------+
                                      |
                                      v
+------------------------------------------------------------------------------------+
|  Query & Filter API: `GET /events`                                                 |
|  Filters: ?session_id=... &event_type=... &severity=... &limit=...                 |
+------------------------------------------------------------------------------------+
```

---

## 2. Event Classification and Schema

### 2.1 Event Types and Severities

| Event Type | Typical Sources | Severity Levels | Example Description |
|---|---|---|---|
| `ARRHYTHMIA` | ML Rhythm Classifier, R-peak detector | `WARNING`, `CRITICAL` | Ventricular Premature Contraction detected |
| `ALERT` | Multimodal Late Fusion Engine | `WARNING`, `CRITICAL` | SBP < 90 mmHg (Hypotension) with tachycardia |
| `EVIDENCE_INGESTED` | Evidence Ingestion Service | `INFO` | Ingested vitals CSV (3 rows) with SHA-256 |
| `REPLAY_CONTROL` | Operator Replay Controls | `INFO` | Replay seek to t=14.50s |
| `SCENARIO` | Cardiovascular ODE Engine | `INFO` | What-If Scenario 'Physical Exertion' executed |
| `STATE_RESET` | Session Manager | `INFO` | Session reset requested |

### 2.2 Table Schema (`clinical_events`)

```sql
CREATE TABLE IF NOT EXISTS clinical_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    source_provenance TEXT NOT NULL,
    category TEXT NOT NULL,
    metadata TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_session_time 
ON clinical_events (session_id, timestamp DESC);
```

---

## 3. Timeline Synchronization with the Digital Twin

1. **Click-to-Seek Navigation:**
   Each event card rendered in [`frontend/src/components/EventTimeline.tsx`](file:///c:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/components/EventTimeline.tsx) displays a timestamp tag (`t = X.XXs`). Clicking the card or the timestamp button dispatches an event that sets the active `selectedTimestamp` in the application state.
2. **Synchronized Waveform View:**
   The ECG Waveform Explorer instantly adjusts its view to center on the selected timestamp, displaying the waveform context ($t_{\text{event}} \pm 1.0\text{s}$).
3. **State Querying at Arbitrary Timestamp (`GET /twin/state-at`):**
   Given a historical instant $t_{\text{query}}$, the backend queries the closest observations occurring before or at $t_{\text{query}}$, constructing the exact multi-modal state matrix as it existed at that time without interpolating or fabricating missing modalities.

