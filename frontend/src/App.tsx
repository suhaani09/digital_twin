import { useState, useEffect, useCallback } from 'react';
import { ApiClient } from './api';
import { useDigitalTwinWebSocket } from './useWebSocket';
import type { DigitalTwinState, ScenarioDefinition } from './types';

import { PatientSessionHeader } from './components/PatientSessionHeader';
import { PatientOverview } from './components/PatientOverview';
import { ECGWaveform } from './components/ECGWaveform';
import { TrendChart } from './components/TrendChart';
import { RhythmDiagnosisCard } from './components/RhythmDiagnosisCard';
import { ModalityFusionPanel } from './components/ModalityFusionPanel';
import { HemodynamicsPanel } from './components/HemodynamicsPanel';
import { ScenarioPanel } from './components/ScenarioPanel';
import { EventTimeline } from './components/EventTimeline';
import { ExplainabilityPanel } from './components/ExplainabilityPanel';
import { EvidenceUploadPanel } from './components/EvidenceUploadPanel';
import type { ECGRecordingMetadata } from './types';

export function App() {
  const [patientId, setPatientId] = useState<string>('100');
  const [hrTrend, setHrTrend] = useState<number[]>([]);
  const [rmssdTrend, setRmssdTrend] = useState<number[]>([]);
  const [bpTrend, setBpTrend] = useState<number[]>([]);
  const [presets, setPresets] = useState<ScenarioDefinition[]>([]);

  // Synchronized timestamp state between ECG Explorer and Event Timeline
  const [selectedTimestamp, setSelectedTimestamp] = useState<number | undefined>(undefined);
  const [recordingMetadata, setRecordingMetadata] = useState<ECGRecordingMetadata | null>(null);

  // Connect WebSocket to real backend with stable callback
  const handleStateReceived = useCallback((state: DigitalTwinState) => {
    // Update trends (bounded to 60 points)
    if (state.heart_rate_bpm !== null && state.heart_rate_bpm !== undefined) {
      setHrTrend((prev) => [...prev.slice(-59), state.heart_rate_bpm!]);
    }
    if (state.hrv_metrics?.rmssd_ms) {
      setRmssdTrend((prev) => [...prev.slice(-59), state.hrv_metrics!.rmssd_ms]);
    }
    if (state.hemodynamics?.systolic_bp_mmhg) {
      setBpTrend((prev) => [...prev.slice(-59), state.hemodynamics!.systolic_bp_mmhg]);
    }
  }, []);

  const { status: wsStatus, latestState } = useDigitalTwinWebSocket(handleStateReceived);

  // Fetch preset scenarios, ECG metadata & initial twin state immediately on mount
  useEffect(() => {
    async function initDashboard() {
      try {
        const [presetsRes, stateRes, metaRes] = await Promise.all([
          ApiClient.listPresetScenarios(),
          ApiClient.getTwinState('100'),
          ApiClient.getECGMetadata().catch(() => null),
        ]);
        setPresets(presetsRes.scenarios);
        if (stateRes) {
          handleStateReceived(stateRes);
        }
        if (metaRes) {
          setRecordingMetadata(metaRes);
        }
      } catch (err) {
        console.error('Failed to initialize dashboard data:', err);
      }
    }
    initDashboard();
  }, [handleStateReceived]);

  const handlePatientChanged = (newPid: string) => {
    setPatientId(newPid);
    // Clear trend buffers on session change
    setHrTrend([]);
    setRmssdTrend([]);
    setBpTrend([]);
  };

  const handleReset = () => {
    setHrTrend([]);
    setRmssdTrend([]);
    setBpTrend([]);
  };

  // Fallback state if WebSocket is awaiting initial packet
  const activeState: DigitalTwinState = latestState || {
    patient_id: patientId,
    session_id: `SESSION_${patientId}`,
    current_time: 0,
    is_live_replay: false,
    playback_speed: 1.0,
    latest_observations: {},
    modality_freshness: {},
    ecg_samples: [],
    ecg_fs: 360,
    signal_quality: { status: 'INITIALIZING', is_valid: false, snr_db: 0 },
    patient_context: {
      patient_id: patientId,
      age: 58,
      gender: 'M',
      medical_history: ['Hypertension', 'History of CAD'],
      active_medications: ['Metoprolol 50mg', 'Aspirin 81mg'],
    },
    clinical_risk_score: { news2_score: 0, risk_category: 'LOW', evidence: {} },
    active_alerts: [],
  };

  return (
    <div className="min-h-screen bg-[#070b12] text-slate-100 flex flex-col font-sans">
      {/* 1. Patient & Session Header Bar */}
      <PatientSessionHeader
        patientId={patientId}
        sessionId={activeState.session_id}
        isLiveReplay={activeState.is_live_replay}
        playbackSpeed={activeState.playback_speed}
        connectionStatus={wsStatus}
        onPatientChanged={handlePatientChanged}
        onReset={handleReset}
      />

      {/* Main Grid Layout */}
      <main className="flex-1 p-3 md:p-4 max-w-[1600px] w-full mx-auto space-y-3">
        {/* Row 1: Patient Context & Hemodynamic Vitals */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-1">
            <PatientOverview context={activeState.patient_context} currentTimeSec={activeState.current_time} />
          </div>
          <div className="lg:col-span-2">
            <HemodynamicsPanel
              hemodynamics={activeState.hemodynamics}
              hrBpm={activeState.heart_rate_bpm}
              glucoseMgDl={activeState.blood_glucose_mg_dl}
            />
          </div>
        </div>

        {/* Row 2: ECG Oscilloscope Waveform & Rhythm Classifier */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-2">
            <ECGWaveform
              samples={activeState.ecg_samples}
              fs={activeState.ecg_fs}
              qualityStatus={activeState.signal_quality.status}
              snrDb={activeState.signal_quality.snr_db}
              isReplay={activeState.is_live_replay}
              selectedTimestamp={selectedTimestamp}
              onTimestampSelected={(t) => setSelectedTimestamp(t)}
              metadata={recordingMetadata}
            />
          </div>
          <div className="lg:col-span-1">
            <RhythmDiagnosisCard
              prediction={activeState.latest_prediction}
              sqiStatus={activeState.signal_quality.status}
              snrDb={activeState.signal_quality.snr_db}
            />
          </div>
        </div>

        {/* Row 3: Trend Charts (HR, RMSSD, SBP) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <TrendChart
            title="Heart Rate Trend"
            unit="bpm"
            data={hrTrend}
            color="#10b981"
            minVal={40}
            maxVal={160}
            nominalRange={[60, 100]}
          />
          <TrendChart
            title="HRV Time-Domain (RMSSD)"
            unit="ms"
            data={rmssdTrend}
            color="#8b5cf6"
            minVal={10}
            maxVal={80}
            nominalRange={[20, 50]}
          />
          <TrendChart
            title="Systolic Arterial Pressure"
            unit="mmHg"
            data={bpTrend}
            color="#38bdf8"
            minVal={70}
            maxVal={180}
            nominalRange={[90, 130]}
          />
        </div>

        {/* Row 4: Evidence Ingestion & Multimodal Fusion */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <EvidenceUploadPanel
            patientId={patientId}
            sessionId={activeState.session_id}
            onEvidenceUploaded={() => {
              // Refresh metadata when new ECG or evidence uploaded
              ApiClient.getECGMetadata().then(setRecordingMetadata).catch(() => null);
            }}
          />
          <ModalityFusionPanel
            freshnessMap={activeState.modality_freshness}
            riskScore={activeState.clinical_risk_score}
          />
        </div>

        {/* Row 5: Clinical Event Timeline & Audit Log */}
        <div className="grid grid-cols-1 gap-3">
          <EventTimeline
            alerts={activeState.active_alerts}
            simTimeSec={activeState.current_time}
            sessionId={activeState.session_id}
            onEventSelected={(t) => setSelectedTimestamp(t)}
          />
        </div>

        {/* Row 6: What-If Simulation Experiments & Explainability */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-2">
            <ScenarioPanel presets={presets} />
          </div>
          <div className="lg:col-span-1">
            <ExplainabilityPanel />
          </div>
        </div>
      </main>

      <footer className="border-t border-slate-800/80 px-4 py-2 text-center text-[11px] text-slate-500 font-mono">
        PhysioTwin Digital Twin Dashboard | Non-diagnostic Demonstration | Ready for Unity Visualization Client
      </footer>
    </div>
  );
}

export default App;
