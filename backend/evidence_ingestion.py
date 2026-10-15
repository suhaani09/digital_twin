"""
Evidence Ingestion Pipeline.

Supports safe parsing, validation, and metadata extraction for:
1. CSV time-series telemetry (e.g. Heart Rate, Blood Pressure, Glucose, SpO2)
   - Required schema: timestamp (seconds or iso), modality/channel, value, unit.
2. ECG files (CSV format: 'sample' or 'lead_ii', 'timestamp_sec', fs)
3. Clinical documents (PDF reports) via pypdf:
   - Secure text extraction, keyword extraction for laboratory/EHR markers,
     strict non-diagnostic annotation.
"""

import hashlib
import io
import time
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pypdf import PdfReader

from backend.event_store import ClinicalEvent, event_store
from backend.schemas import DataSourceType, ModalityType, RawObservation


class EvidenceIngestionService:
    def __init__(self, upload_dir: str = "data/uploads"):
        self.upload_dir = upload_dir

    @staticmethod
    def compute_sha256(file_bytes: bytes) -> str:
        return hashlib.sha256(file_bytes).hexdigest()

    def process_csv_evidence(
        self,
        file_bytes: bytes,
        filename: str,
        session_id: str,
        patient_id: str,
    ) -> Tuple[Dict[str, Any], List[RawObservation]]:
        """
        Parses CSV evidence into validated observation list.
        Supports standard header formats:
        Format A (Multi-variable): timestamp,modality,value,unit
        Format B (ECG column): ecg / lead_ii / sample with optional timestamp or uniform dt.
        """
        file_hash = self.compute_sha256(file_bytes)
        upload_time = time.time()
        file_size = len(file_bytes)

        try:
            df = pd.read_csv(io.BytesIO(file_bytes))
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {str(e)}")

        df.columns = [c.strip().lower() for c in df.columns]
        observations: List[RawObservation] = []
        extracted_summary: Dict[str, Any] = {}

        # Case 1: ECG Stream in CSV (e.g. 'ecg', 'lead_ii', or 'mv')
        ecg_col = next((c for c in df.columns if c in ["ecg", "lead_ii", "mlii", "voltage_mv", "sample"]), None)
        if ecg_col:
            samples = df[ecg_col].dropna().values.astype(float)
            fs = 360.0  # default or infer from dt
            if "timestamp" in df.columns or "time" in df.columns:
                t_col = "timestamp" if "timestamp" in df.columns else "time"
                times = df[t_col].dropna().values.astype(float)
                if len(times) > 1:
                    dt = float(np.mean(np.diff(times)))
                    if dt > 0:
                        fs = round(1.0 / dt, 1)

            acq_time = float(df["timestamp"].iloc[0]) if "timestamp" in df.columns else 0.0

            # Store summary
            extracted_summary = {
                "evidence_type": "ECG_TIMESERIES",
                "sample_count": len(samples),
                "sampling_frequency_hz": fs,
                "duration_seconds": round(len(samples) / fs, 2),
                "detected_lead": "Lead II",
                "amplitude_range_mv": [round(float(np.min(samples)), 3), round(float(np.max(samples)), 3)],
            }

            # Create an observation chunk
            obs = RawObservation(
                patient_id=patient_id,
                session_id=session_id,
                modality=ModalityType.ECG_CHUNK,
                timestamp=acq_time,
                values={"samples": [round(float(s), 4) for s in samples[:2000]], "fs": fs},
                unit="mV",
                source_type=DataSourceType.MANUAL_INGEST,
                provenance=f"CSV Upload: {filename} (Hash: {file_hash[:8]})",
            )
            observations.append(obs)

        # Case 2: Multi-modal table (timestamp, modality, value, unit)
        elif "modality" in df.columns and "value" in df.columns:
            modalities_found = set()
            for _, row in df.iterrows():
                mod_str = str(row["modality"]).strip().lower()
                val = float(row["value"])
                u = str(row.get("unit", "")).strip()
                t = float(row.get("timestamp", 0.0))

                mod_type = None
                val_dict = {}
                if "hr" in mod_str or "heart" in mod_str:
                    mod_type = ModalityType.HEART_RATE
                    val_dict = {"bpm": val}
                    u = u or "bpm"
                elif "glu" in mod_str:
                    mod_type = ModalityType.BLOOD_GLUCOSE
                    val_dict = {"mg_dl": val}
                    u = u or "mg/dL"
                elif "sbp" in mod_str or "bp" in mod_str or "pressure" in mod_str:
                    mod_type = ModalityType.BLOOD_PRESSURE
                    val_dict = {"systolic_bp": val}
                    u = u or "mmHg"

                if mod_type:
                    modalities_found.add(mod_type.value)
                    observations.append(
                        RawObservation(
                            patient_id=patient_id,
                            session_id=session_id,
                            modality=mod_type,
                            timestamp=t,
                            values=val_dict,
                            unit=u,
                            source_type=DataSourceType.MANUAL_INGEST,
                            provenance=f"CSV Upload: {filename}",
                        )
                    )

            acq_time = float(df["timestamp"].iloc[0]) if "timestamp" in df.columns else 0.0
            extracted_summary = {
                "evidence_type": "MULTIMODAL_MEASUREMENTS",
                "rows_parsed": len(df),
                "modalities_extracted": list(modalities_found),
                "time_span_seconds": round(float(df["timestamp"].max() - df["timestamp"].min()), 2) if "timestamp" in df.columns else 0.0,
            }
        else:
            raise ValueError("CSV missing supported columns. Expected ('ecg'/'lead_ii') or ('modality','value').")

        # Record in evidence registry and audit event store
        evidence_id = f"EV_{patient_id}_{file_hash[:10]}"
        event_store.record_evidence(
            evidence_id=evidence_id,
            session_id=session_id,
            filename=filename,
            file_type="CSV",
            file_hash=file_hash,
            file_size_bytes=file_size,
            upload_timestamp=upload_time,
            acquisition_timestamp=acq_time,
            source_provenance=f"User Upload ({filename})",
            extracted_summary=extracted_summary,
            status="SUCCESS",
        )

        event_store.record_event(
            ClinicalEvent(
                event_id=f"EVT_{evidence_id}",
                session_id=session_id,
                timestamp=round(acq_time, 2),
                event_type="EVIDENCE_UPLOAD",
                severity="INFO",
                description=f"CSV Evidence '{filename}' uploaded ({extracted_summary.get('evidence_type')}, {len(observations)} observations).",
                source_provenance=f"Evidence Registry ({filename})",
                evidence_id=evidence_id,
                category="OBSERVED",
                metadata=extracted_summary,
            )
        )

        return extracted_summary, observations

    def process_pdf_evidence(
        self,
        file_bytes: bytes,
        filename: str,
        session_id: str,
        patient_id: str,
    ) -> Tuple[Dict[str, Any], List[RawObservation]]:
        """
        Parses clinical PDF document, extracts text safely, discovers vital sign references,
        and annotates as non-diagnostic document evidence.
        """
        file_hash = self.compute_sha256(file_bytes)
        upload_time = time.time()
        file_size = len(file_bytes)

        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            full_text = ""
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
        except Exception as e:
            raise ValueError(f"Failed to parse PDF document: {str(e)}")

        # Extract keyword markers without making clinical diagnoses
        extracted_markers: Dict[str, Any] = {}
        text_lower = full_text.lower()

        # Keyword discovery: Blood pressure, Heart rate, Glucose
        import re
        hr_match = re.search(r"(?:heart\s*rate|hr|pulse)[:\s]*([0-9]{2,3})\s*(?:bpm)?", text_lower)
        if hr_match:
            extracted_markers["extracted_heart_rate_bpm"] = float(hr_match.group(1))

        bp_match = re.search(r"(?:blood\s*pressure|bp)[:\s]*([0-9]{2,3})\s*/\s*([0-9]{2,3})", text_lower)
        if bp_match:
            extracted_markers["extracted_bp_systolic"] = float(bp_match.group(1))
            extracted_markers["extracted_bp_diastolic"] = float(bp_match.group(2))

        glu_match = re.search(r"(?:glucose|blood\s*sugar)[:\s]*([0-9]{2,3})\s*(?:mg/dl)?", text_lower)
        if glu_match:
            extracted_markers["extracted_glucose_mg_dl"] = float(glu_match.group(1))

        extracted_summary = {
            "evidence_type": "CLINICAL_DOCUMENT_PDF",
            "page_count": len(reader.pages),
            "total_character_count": len(full_text),
            "extracted_biomarkers": extracted_markers,
            "clinical_interpretation_disclaimer": "Automated text extraction only. No clinical diagnosis or medical report validation performed.",
        }

        evidence_id = f"EV_{patient_id}_{file_hash[:10]}"
        event_store.record_evidence(
            evidence_id=evidence_id,
            session_id=session_id,
            filename=filename,
            file_type="PDF",
            file_hash=file_hash,
            file_size_bytes=file_size,
            upload_timestamp=upload_time,
            acquisition_timestamp=upload_time,
            source_provenance=f"User PDF Upload ({filename})",
            extracted_summary=extracted_summary,
            status="PARSED_TEXT_ONLY",
        )

        event_store.record_event(
            ClinicalEvent(
                event_id=f"EVT_{evidence_id}",
                session_id=session_id,
                timestamp=round(upload_time, 2),
                event_type="EVIDENCE_UPLOAD",
                severity="INFO",
                description=f"Clinical PDF '{filename}' uploaded ({len(reader.pages)} pages, {len(extracted_markers)} biomarkers discovered).",
                source_provenance=f"Evidence Registry ({filename})",
                evidence_id=evidence_id,
                category="OBSERVED",
                metadata=extracted_summary,
            )
        )

        return extracted_summary, []


# Global evidence ingestion instance
evidence_service = EvidenceIngestionService()

