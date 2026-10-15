# Evidence Ingestion Architecture

## 1. Overview and Ingestion Principles

The Evidence Ingestion pipeline (`backend/evidence_ingestion.py`) provides an auditable gateway for assimilating external clinical artifacts—including wearable multi-modal timeseries (CSV), single-lead or multi-lead raw ECG dumps (CSV), and digitized medical reports or lab notes (PDF).

```
+-----------------------------------------------------------------------------------------+
|                                EVIDENCE INGESTION PIPELINE                              |
+-----------------------------------------------------------------------------------------+
|  Input File (CSV or PDF)                                                                |
|         |                                                                               |
|         v                                                                               |
|  [Cryptographic Integrity] ---> SHA-256 Checksum Calculation & File Size Validation     |
|         |                                                                               |
|         +---> [Format Detection & Parser Router]                                        |
|                     |                                                                   |
|                     +---> [CSV Parser]                                                  |
|                     |        |                                                          |
|                     |        +---> Timeseries ECG Stream (Load into Replay Engine)      |
|                     |        +---> Multimodal Vitals (Ingest into Fusion State Buffer)   |
|                     |                                                                   |
|                     +---> [PDF Parser with pypdf]                                       |
|                              |                                                          |
|                              +---> Text Extraction & Metadata Inspection                |
|                              +---> Regex Biomarker Discovery (HR, SBP, DBP, Glucose)     |
|                              +---> Strict Non-Diagnostic Annotation Disclaimer          |
|                                                                                         |
|         v                                                                               |
|  [SQLite Evidence Registry & Clinical Audit Log] (`data/events.db`)                     |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Ingestion Routes and Formats

### 2.1 File Integrity and Hash Tracking
Every file ingested through `POST /evidence/upload` generates a SHA-256 cryptographic digest before any parsing or transformation occurs:
```python
sha256_hash = hashlib.sha256(file_bytes).hexdigest()
```
This hash is stored in `evidence_registry` and linked to generated clinical events, creating a tamper-evident audit trail for clinical researchers.

### 2.2 CSV Telemetry Streams
The CSV parser automatically discriminates between two distinct formats:
1. **Raw ECG Waveform Stream:**
   - Columns: `timestamp,ecg` or `timestamp,amplitude` (or headerless single-column numbers).
   - Dynamically calculates the effective sample rate ($f_s = 1 / \Delta t$) or adopts a configurable standard (default $360\text{ Hz}$).
   - Emits `RawObservation` of type `ECG_CHUNK` and registers the waveform directly into [`backend/replay_engine.py`](file:///c:/Users/Suhani%20Thakur/healthcare-digital-twin/backend/replay_engine.py) for playback.
2. **Multimodal Vitals Log:**
   - Columns: `timestamp,modality,value,unit` (with optional `source` column).
   - Validates modalities against `ModalityType` (`heart_rate`, `blood_pressure`, `blood_glucose`, `hrv_metrics`).
   - Streams observations into the `MultimodalFusionEngine` state manager with complete timestamp preservation.

### 2.3 PDF Clinical Reports
Parsed via `pypdf`:
- Extracts text content across all pages.
- Identifies page count, text character length, and document metadata.
- Applies deterministic regular expressions to discover mentioned physiological indicators:
  - Heart Rate (`(?i)(?:hr|heart\s*rate|pulse)\s*[:=]?\s*(\d{2,3})`)
  - Blood Pressure (`(?i)(?:bp|blood\s*pressure)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})`)
  - Blood Glucose (`(?i)(?:glucose|blood\s*sugar)\s*[:=]?\s*(\d{2,3})`)
- **Strict Non-Diagnostic Safeguard:** All PDF-extracted indicators are explicitly cataloged as contextual text extractions, not validated diagnostic measurements. A non-negotiable banner is attached:
  > *"Research/demonstration artifact only. Extracted values must not be utilized for medical diagnosis or clinical intervention without secondary verification."*

---

## 3. Database Schema (`evidence_registry`)

Defined in [`backend/event_store.py`](file:///c:/Users/Suhani%20Thakur/healthcare-digital-twin/backend/event_store.py):

| Column | Type | Description |
|---|---|---|
| `evidence_id` | TEXT PRIMARY KEY | Formatted as `EVID_<SHA256[:16]>_<TIMESTAMP>` |
| `session_id` | TEXT | Linked session identifier |
| `patient_id` | TEXT | Linked patient identifier |
| `filename` | TEXT | Original upload filename |
| `file_type` | TEXT | `csv`, `pdf`, etc. |
| `file_size_bytes` | INTEGER | Exact byte count |
| `sha256_hash` | TEXT | Cryptographic SHA-256 fingerprint |
| `uploaded_at` | REAL | Epoch timestamp |
| `summary` | TEXT | JSON summary of parsed contents |
| `diagnostic_disclaimer` | TEXT | Non-diagnostic notice |

