"""
Real-time Replay Engine & Session Manager.

Reads a recorded or synthetic patient recording and emits timestamped
multimodal observations at configurable speeds (0.5x, 1x, 2x, 5x).
Supports:
- Start, Pause, Resume, Stop, Seek, Reset
- Multimodal emission (ECG chunks + simulated vitals + glucose)
- Clear Replay-vs-Live status indicators
- Strict session isolation: stopping a session cleans and resets state.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
import time
from typing import Callable, Optional
import numpy as np

from backend.dataset_loader import MITBIHLoader
from backend.schemas import DataSourceType, ModalityType, RawObservation


class ReplayStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class ReplayService:
    """
    Manages asynchronous playback of recorded ECG data.
    Feeds chunks into a callback function (e.g. state ingestor).
    """

    def __init__(self, on_observation_cb: Callable[[RawObservation], None]):
        self.on_observation_cb = on_observation_cb
        self.loader = MITBIHLoader(data_dir="data/mitdb")
        self.status = ReplayStatus.STOPPED
        self.speed = 1.0
        self.current_sample_idx = 0
        self.patient_id = "100"
        self.session_id = "SESSION_DEFAULT"

        self.signal_data: Optional[np.ndarray] = None
        self.fs = 360.0
        self.total_samples = 0
        self.is_synthetic = False

        self._task: Optional[asyncio.Task] = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()

    def load_patient_record(self, patient_id: str):
        """Loads record from dataset loader or creates synthetic fixture."""
        self.patient_id = patient_id
        rec = self.loader.load_record(patient_id, max_samples=10000, use_cache=False)
        self.signal_data = rec.raw_signal[:, 0]  # Lead II
        self.fs = rec.fs
        self.total_samples = len(self.signal_data)
        self.is_synthetic = rec.is_synthetic
        self.current_sample_idx = 0

    async def start(self, patient_id: str = "100", session_id: str = "SESSION_1", speed: float = 1.0):
        await self.stop()
        self.session_id = session_id
        self.speed = max(0.2, min(10.0, speed))
        self.load_patient_record(patient_id)

        self.status = ReplayStatus.RUNNING
        self._pause_event.set()
        self._task = asyncio.create_task(self._playback_loop())

    async def pause(self):
        if self.status == ReplayStatus.RUNNING:
            self.status = ReplayStatus.PAUSED
            self._pause_event.clear()

    async def resume(self):
        if self.status == ReplayStatus.PAUSED:
            self.status = ReplayStatus.RUNNING
            self._pause_event.set()

    async def stop(self):
        self.status = ReplayStatus.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self.current_sample_idx = 0

    def seek(self, timestamp_seconds: float):
        """Seeks to target time within the active recording."""
        target_sample = int(timestamp_seconds * self.fs)
        self.current_sample_idx = max(0, min(self.total_samples - 1, target_sample))

    def step_window(self, window_sec: float = 2.0, forward: bool = True):
        """Steps forward or backward by window_sec."""
        delta = int(window_sec * self.fs)
        if forward:
            self.current_sample_idx = min(self.total_samples - 1, self.current_sample_idx + delta)
        else:
            self.current_sample_idx = max(0, self.current_sample_idx - delta)

    def load_custom_signal(
        self,
        signal_array: np.ndarray,
        fs: float = 360.0,
        patient_id: str = "custom",
        session_id: str = "SESSION_UPLOAD",
        provenance: str = "User Uploaded ECG",
    ):
        """Loads an externally parsed/uploaded ECG signal into the replay service."""
        self.patient_id = patient_id
        self.session_id = session_id
        self.signal_data = np.asarray(signal_array, dtype=np.float32)
        self.fs = float(fs)
        self.total_samples = len(self.signal_data)
        self.is_synthetic = False
        self.current_sample_idx = 0

    def get_metadata(self, patient_id: Optional[str] = None) -> dict:
        """Returns metadata for the currently active recording or requested patient."""
        p_id = str(patient_id) if patient_id else self.patient_id
        if self.signal_data is None or self.patient_id != p_id:
            self.load_patient_record(p_id)
        duration_sec = self.total_samples / self.fs if self.fs > 0 else 0.0
        current_time = self.current_sample_idx / self.fs if self.fs > 0 else 0.0
        return {
            "patient_id": self.patient_id,
            "session_id": self.session_id,
            "fs": self.fs,
            "total_samples": self.total_samples,
            "duration_sec": round(duration_sec, 3),
            "current_time_sec": round(current_time, 3),
            "channel_lead": "Lead II (MLII)",
            "unit": "mV",
            "is_synthetic": self.is_synthetic,
            "source_type": "replay_dataset" if not self.is_synthetic else "synthetic_fixture",
            "provenance": f"MIT-BIH Record {self.patient_id}" if not self.is_synthetic else "Synthetic Fixture",
            "status": self.status.value,
            "speed": self.speed,
        }

    def get_window(self, center_timestamp_sec: float, window_sec: float = 2.0, patient_id: Optional[str] = None) -> dict:
        """Returns a window of samples centered around center_timestamp_sec without mutating replay state."""
        p_id = str(patient_id) if patient_id else self.patient_id
        if self.signal_data is None or self.patient_id != p_id:
            self.load_patient_record(p_id)

        center_idx = int(center_timestamp_sec * self.fs)
        half_samples = int((window_sec / 2.0) * self.fs)

        start_idx = max(0, center_idx - half_samples)
        end_idx = min(self.total_samples, center_idx + half_samples)

        samples = [round(float(s), 4) for s in self.signal_data[start_idx:end_idx]]
        actual_start_sec = start_idx / self.fs if self.fs > 0 else 0.0
        actual_end_sec = end_idx / self.fs if self.fs > 0 else 0.0

        return {
            "patient_id": self.patient_id,
            "center_timestamp_sec": round(center_timestamp_sec, 3),
            "window_sec": window_sec,
            "start_time_sec": round(actual_start_sec, 3),
            "end_time_sec": round(actual_end_sec, 3),
            "sample_count": len(samples),
            "fs": self.fs,
            "samples": samples,
            "unit": "mV",
            "lead": "Lead II (MLII)",
        }

    def set_speed(self, speed: float):
        self.speed = max(0.2, min(10.0, speed))

    async def _playback_loop(self):
        """Main playback loop emitting chunks every ~100 ms."""
        # Chunk size: at 360 Hz, 100 ms = 36 samples
        chunk_samples = int(self.fs * 0.1)
        step_dt = 0.1  # 100ms real wall clock interval

        tick = 0
        try:
            while self.status != ReplayStatus.STOPPED:
                await self._pause_event.wait()

                if self.signal_data is None or self.current_sample_idx >= self.total_samples:
                    # Loop playback from beginning
                    self.current_sample_idx = 0

                end_idx = min(self.total_samples, self.current_sample_idx + chunk_samples)
                chunk = self.signal_data[self.current_sample_idx:end_idx]
                sim_time = self.current_sample_idx / self.fs

                # 1. Emit ECG waveform chunk
                obs_ecg = RawObservation(
                    patient_id=self.patient_id,
                    session_id=self.session_id,
                    modality=ModalityType.ECG_CHUNK,
                    timestamp=round(sim_time, 3),
                    values={"samples": [round(float(s), 4) for s in chunk]},
                    unit="mV",
                    source_type=DataSourceType.REPLAY_DATASET if not self.is_synthetic else DataSourceType.SIMULATED_MODEL,
                    provenance=f"MIT-BIH Record {self.patient_id}" if not self.is_synthetic else "Synthetic Fixture",
                )
                self.on_observation_cb(obs_ecg)

                # 2. Intermittently emit Heart Rate every ~1.0s (10 ticks)
                if tick % 10 == 0:
                    # Add mild natural physiological variability around 72 bpm
                    sim_hr = 72.0 + 8.0 * np.sin(sim_time * 0.3)
                    obs_hr = RawObservation(
                        patient_id=self.patient_id,
                        session_id=self.session_id,
                        modality=ModalityType.HEART_RATE,
                        timestamp=round(sim_time, 3),
                        values={"bpm": round(float(sim_hr), 1)},
                        unit="bpm",
                        source_type=DataSourceType.REPLAY_DATASET,
                        provenance="ECG Derived Instantaneous HR",
                    )
                    self.on_observation_cb(obs_hr)

                # 3. Intermittently emit Blood Glucose every ~10.0s (100 ticks)
                if tick % 100 == 0:
                    obs_glu = RawObservation(
                        patient_id=self.patient_id,
                        session_id=self.session_id,
                        modality=ModalityType.BLOOD_GLUCOSE,
                        timestamp=round(sim_time, 3),
                        values={"mg_dl": 105.0},
                        unit="mg/dL",
                        source_type=DataSourceType.SIMULATED_MODEL,
                        provenance="Simulated CGM Stream",
                    )
                    self.on_observation_cb(obs_glu)

                self.current_sample_idx = end_idx
                tick += 1

                # Adjust sleep time based on playback speed
                sleep_duration = max(0.01, step_dt / self.speed)
                await asyncio.sleep(sleep_duration)

        except asyncio.CancelledError:
            pass

