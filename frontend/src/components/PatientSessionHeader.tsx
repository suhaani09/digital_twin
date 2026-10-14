import React, { useState } from 'react';
import { ApiClient } from '../api';
import { Play, Pause, Square, RotateCcw } from 'lucide-react';

interface PatientSessionHeaderProps {
  patientId: string;
  sessionId: string;
  isLiveReplay: boolean;
  playbackSpeed: number;
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error';
  onPatientChanged?: (newPatientId: string) => void;
  onReset?: () => void;
}

export const PatientSessionHeader: React.FC<PatientSessionHeaderProps> = ({
  patientId,
  sessionId,
  isLiveReplay,
  playbackSpeed,
  connectionStatus,
  onPatientChanged,
  onReset,
}) => {
  const [selectedPid, setSelectedPid] = useState(patientId);
  const [isLoading, setIsLoading] = useState(false);

  const availablePatients = ['100', '101', '103', '106', '108', '119', '205'];

  const handlePatientSelect = async (newPid: string) => {
    setSelectedPid(newPid);
    setIsLoading(true);
    try {
      await ApiClient.selectSession(newPid, `SESSION_${newPid}`);
      if (onPatientChanged) onPatientChanged(newPid);
    } catch (err) {
      console.error('Failed to change session patient:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReplayAction = async (action: 'start' | 'pause' | 'resume' | 'stop') => {
    try {
      await ApiClient.controlReplay(action, { patient_id: selectedPid, speed: playbackSpeed });
    } catch (err) {
      console.error(`Replay ${action} failed:`, err);
    }
  };

  const handleSpeedChange = async (speed: number) => {
    try {
      await ApiClient.controlReplay('speed', { speed });
    } catch (err) {
      console.error('Speed change failed:', err);
    }
  };

  const handleReset = async () => {
    try {
      await ApiClient.resetTwin(selectedPid);
      if (onReset) onReset();
    } catch (err) {
      console.error('Reset failed:', err);
    }
  };

  return (
    <header className="bg-slate-900 border-b border-slate-800 px-4 py-2.5 flex flex-wrap items-center justify-between gap-3">
      {/* Title & Connection Status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse shadow-sm shadow-emerald-500/50"></div>
          <h1 className="text-sm font-bold tracking-wider text-slate-100 uppercase">
            PhysioTwin <span className="text-xs font-normal text-slate-400">Clinical Dashboard</span>
          </h1>
        </div>

        <div className="h-4 w-px bg-slate-800"></div>

        {/* WebSocket Connection Pill */}
        <div className="flex items-center gap-1.5 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              connectionStatus === 'connected'
                ? 'bg-emerald-400'
                : connectionStatus === 'connecting'
                ? 'bg-amber-400 animate-pulse'
                : 'bg-rose-500'
            }`}
          ></span>
          <span className="text-slate-400 font-mono text-[11px] uppercase">{connectionStatus}</span>
        </div>
      </div>

      {/* Patient & Session Selection */}
      <div className="flex items-center gap-3 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-slate-400">Patient:</span>
          <select
            value={selectedPid}
            disabled={isLoading}
            onChange={(e) => handlePatientSelect(e.target.value)}
            className="bg-slate-950 border border-slate-700 text-slate-200 rounded px-2 py-1 text-xs focus:outline-none focus:border-indigo-500"
          >
            {availablePatients.map((pid) => (
              <option key={pid} value={pid}>
                PhysioNet #{pid}
              </option>
            ))}
          </select>
        </div>

        <div className="text-slate-500 font-mono text-[11px]">
          Session: <span className="text-slate-300">{sessionId}</span>
        </div>

        <button
          onClick={handleReset}
          title="Reset digital twin state & clear buffers"
          className="btn btn-secondary flex items-center gap-1 text-[11px] py-1 px-2"
        >
          <RotateCcw className="w-3 h-3" />
          <span>Reset</span>
        </button>
      </div>

      {/* Replay Controls */}
      <div className="flex items-center gap-2 bg-slate-950 px-2.5 py-1 rounded border border-slate-800 text-xs">
        <span className="text-[11px] text-slate-400 font-medium">Replay:</span>

        {!isLiveReplay ? (
          <button
            onClick={() => handleReplayAction('start')}
            className="text-emerald-400 hover:text-emerald-300 p-1 transition"
            title="Start Replay"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
          </button>
        ) : (
          <button
            onClick={() => handleReplayAction('pause')}
            className="text-amber-400 hover:text-amber-300 p-1 transition"
            title="Pause Replay"
          >
            <Pause className="w-3.5 h-3.5 fill-current" />
          </button>
        )}

        <button
          onClick={() => handleReplayAction('stop')}
          className="text-rose-400 hover:text-rose-300 p-1 transition"
          title="Stop Replay"
        >
          <Square className="w-3.5 h-3.5 fill-current" />
        </button>

        <div className="h-3 w-px bg-slate-800 mx-1"></div>

        {/* Speed Knobs */}
        <div className="flex items-center gap-1 text-[10px] font-mono">
          {[1.0, 2.0, 5.0].map((s) => (
            <button
              key={s}
              onClick={() => handleSpeedChange(s)}
              className={`px-1.5 py-0.5 rounded transition ${
                playbackSpeed === s
                  ? 'bg-indigo-600 text-white font-bold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>
    </header>
  );
};
