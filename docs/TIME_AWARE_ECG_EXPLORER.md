# Time-Aware ECG Explorer & Replay Architecture

## 1. Overview and Core Purpose

The Time-Aware ECG Explorer equips clinicians, biomedical researchers, and AI evaluators with the ability to navigate historical and live ECG recordings with millisecond precision. Rather than treating an ECG as an ephemeral rolling animation buffer, the digital twin retains the full contiguous recording metadata, sample rate, voltage resolution, and timing provenance.

```
+-----------------------------------------------------------------------------------+
|                           TIME-AWARE ECG EXPLORER                                 |
+-----------------------------------------------------------------------------------+
|  [<< -2s]  [Seek Bar: 0.00s ========|========= 60.00s]  [+2s >>]  [Window: 2.0s]  |
|                                                                                   |
|  * Replay Status: RUNNING | PAUSED | STOPPED                                     |
|  * Lead: MLII (Primary Lead)                                                     |
|  * Sampling Rate: 360.0 Hz                                                        |
|  * Voltage Resolution: mV (Amplitude Scale +/- 2.5 mV)                           |
|  * Mode: LIVE STREAM (10 Hz WebSocket) <---> HISTORICAL INSPECTION (/ecg/window)  |
+-----------------------------------------------------------------------------------+
```

---

## 2. Timing and Windowing Architecture

### 2.1 Metadata Preservation
When an ECG record is loaded (e.g. MIT-BIH record `100` or custom uploaded telemetry), [`backend/replay_engine.py`](file:///c:/Users/Suhani%20Thakur/healthcare-digital-twin/backend/replay_engine.py) exposes the complete physical parameters via `GET /ecg/metadata`:

- **Sampling Frequency ($f_s$):** MIT-BIH Arrhythmia standard $360.0\text{ Hz}$ ($T_s \approx 2.778\text{ ms}$). Custom streams support variable frequencies (e.g. $100\text{ Hz} - 1000\text{ Hz}$).
- **Recording Time Range:** Normalized elapsed time $[0.0, T_{\text{total}}]$, along with wall-clock epoch timestamp reference.
- **Lead / Channel Configuration:** Primary channel designated (e.g., `MLII`, `V1`, `Lead II`).
- **Physical Calibration:** Amplitude expressed strictly in millivolts ($\text{mV}$); ADC offset and gain conversions are computed prior to ingestion.

### 2.2 Microsecond-Accurate Window Extraction
The endpoint `GET /ecg/window` extracts a slice of raw signal without modifying or downsampling the underlying array:
$$\text{center\_idx} = \text{round}(t_{\text{center}} \times f_s)$$
$$\text{half\_window} = \text{round}\left(\frac{\text{window\_sec} \times f_s}{2}\right)$$
$$\text{slice\_indices} = [\max(0, \text{center\_idx} - \text{half\_window}), \min(N, \text{center\_idx} + \text{half\_window})]$$

Each returned payload contains:
- `patient_id` and `session_id`
- `center_timestamp_sec`
- `window_sec` (e.g., 1.0s, 2.0s, 5.0s)
- `sample_rate_hz`
- `lead_name` and `unit`
- `timestamps`: Array of exact timestamps relative to session start $[t_0, t_1, \dots, t_k]$
- `samples`: Calibrated float array in millivolts

---

## 3. UI Navigation and Bidirectional Synchronization

### 3.1 Step Controls and Seek Bar
The React frontend component [`frontend/src/components/ECGWaveform.tsx`](file:///c:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/components/ECGWaveform.tsx) features:
1. **Scrubbing Slider:** Bounded by `[0, total_duration_sec]`, allowing continuous random access to any instant in the recording.
2. **Step Buttons (`-2s` / `+2s`):** Increments or decrements the inspection window by exactly 2.0 seconds. If replay is active, issuing a step control automatically pauses the live stream to prevent display jitter.
3. **Window Width Selector:** Toggles between $1.0\text{s}$ (focused morphology view), $2.0\text{s}$ (rhythm context), and $5.0\text{s}$ (bradycardia/tachycardia episode analysis).
4. **"Return to Live" Action:** Clear button that restores real-time streaming mode from the active WebSocket feed.

### 3.2 Event-to-Waveform Navigation
When a user clicks on an anomaly or alert in the **Clinical Event Timeline** (e.g. an arrhythmia event at $t = 14.50\text{s}$), the dashboard updates the central `selectedTimestamp` state. The ECG Explorer instantly queries `GET /ecg/window?center_timestamp_sec=14.50&window_sec=2.0` and renders the precise waveform morphology surrounding the clinical alert.

---

## 4. Signal Quality and Bandpass Filtering

1. **Hardware / Transmission Integrity (SQI):** Checked per window via flatline detection ($<0.01\text{ mV}$ std dev) and missing sample ratios ($>5\%$ NaN/Inf triggers `POOR` quality status).
2. **Deterministic Fallback Filtering:** To ensure compatibility on systems enforcing binary security restrictions on compiled SciPy DLLs, [`backend/ecg_processor.py`](file:///c:/Users/Suhani%20Thakur/healthcare-digital-twin/backend/ecg_processor.py) implements a pure NumPy moving-window baseline wander removal and low-pass smoothing filter alongside standard Butterworth IIR routines.

