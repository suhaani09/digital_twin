import React, { useEffect, useRef, useState } from 'react';
import { ApiClient } from '../api';
import type { ECGRecordingMetadata } from '../types';
import { RotateCcw, ChevronLeft, ChevronRight, Activity, Clock, Sliders, Loader2 } from 'lucide-react';

interface ECGWaveformProps {
  samples: number[];
  fs: number;
  width?: number;
  height?: number;
  qualityStatus?: string;
  snrDb?: number;
  isReplay?: boolean;
  selectedTimestamp?: number;
  onTimestampSelected?: (timestamp: number) => void;
  metadata?: ECGRecordingMetadata | null;
}

export const ECGWaveform: React.FC<ECGWaveformProps> = ({
  samples,
  fs = 360,
  width = 750,
  height = 180,
  qualityStatus = 'ACCEPTABLE',
  snrDb = 15.0,
  isReplay = false,
  selectedTimestamp,
  onTimestampSelected,
  metadata,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Time-aware inspection state
  const [inspectMode, setInspectMode] = useState<'LIVE' | 'HISTORICAL'>('LIVE');
  const [targetTime, setTargetTime] = useState<number>(selectedTimestamp || 0.0);
  const [windowSec, setWindowSec] = useState<number>(2.0);
  const [inspectedSamples, setInspectedSamples] = useState<number[]>([]);
  const [inspectMetadata, setInspectMetadata] = useState<{
    startTime: number;
    endTime: number;
    sampleCount: number;
    fs: number;
  } | null>(null);
  const [isLoadingWindow, setIsLoadingWindow] = useState(false);

  // Reset historical inspect state when patient changes
  useEffect(() => {
    if (metadata?.patient_id) {
      setInspectMode('LIVE');
      setInspectedSamples([]);
      setInspectMetadata(null);
      setTargetTime(0.0);
    }
  }, [metadata?.patient_id]);

  // Sync targetTime if parent selectedTimestamp changes (e.g. from event click)
  useEffect(() => {
    if (selectedTimestamp !== undefined && selectedTimestamp !== null) {
      setTargetTime(selectedTimestamp);
      setInspectMode('HISTORICAL');
      fetchWindow(selectedTimestamp, windowSec, metadata?.patient_id);
    }
  }, [selectedTimestamp, metadata?.patient_id]);

  const durationSec = metadata?.duration_sec || 27.78;

  const fetchWindow = async (timeSec: number, winSec: number, pId?: string) => {
    setIsLoadingWindow(true);
    try {
      const res = await ApiClient.getECGWindow(timeSec, winSec, pId || metadata?.patient_id);
      setInspectedSamples(res.samples);
      setInspectMetadata({
        startTime: res.start_time_sec,
        endTime: res.end_time_sec,
        sampleCount: res.sample_count,
        fs: res.fs,
      });
    } catch (err) {
      console.error('Failed to fetch windowed ECG samples:', err);
    } finally {
      setIsLoadingWindow(false);
    }
  };

  const handleTimeSliderChange = (newTime: number) => {
    setTargetTime(newTime);
    setInspectMode('HISTORICAL');
    if (onTimestampSelected) onTimestampSelected(newTime);
    fetchWindow(newTime, windowSec, metadata?.patient_id);
  };

  const handleStepWindow = (forward: boolean) => {
    const delta = forward ? windowSec : -windowSec;
    const nextTime = Math.max(0, Math.min(durationSec, targetTime + delta));
    handleTimeSliderChange(nextTime);
  };

  const handleReturnToLive = () => {
    setInspectMode('LIVE');
    setInspectedSamples([]);
    setInspectMetadata(null);
  };

  // Determine active samples to display
  const activeSamples = inspectMode === 'HISTORICAL' && inspectedSamples.length > 0 ? inspectedSamples : samples;
  const activeFs = inspectMode === 'HISTORICAL' && inspectMetadata ? inspectMetadata.fs : fs;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear background (clinical dark theme)
    ctx.fillStyle = '#090d16';
    ctx.fillRect(0, 0, width, height);

    // Draw clinical medical millimeter grid (25mm/s, 10mm/mV)
    const majorGrid = 25;
    const minorGrid = 5;

    // Minor grid
    ctx.beginPath();
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += minorGrid) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
    }
    for (let y = 0; y < height; y += minorGrid) {
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
    }
    ctx.stroke();

    // Major grid
    ctx.beginPath();
    ctx.strokeStyle = '#1e293b';
    for (let x = 0; x < width; x += majorGrid) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
    }
    for (let y = 0; y < height; y += majorGrid) {
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
    }
    ctx.stroke();

    // Calibration pulse indicator on left (1 mV = 10mm ~ 35px)
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    const midY = height / 2;
    ctx.moveTo(10, midY);
    ctx.lineTo(20, midY);
    ctx.lineTo(20, midY - 35);
    ctx.lineTo(35, midY - 35);
    ctx.lineTo(35, midY);
    ctx.lineTo(45, midY);
    ctx.stroke();

    // Draw ECG waveform
    if (activeSamples.length > 1) {
      ctx.beginPath();
      const isClean = qualityStatus === 'ACCEPTABLE';
      const strokeColor = inspectMode === 'HISTORICAL' ? '#38bdf8' : isClean ? '#10b981' : '#f59e0b';

      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 2.0;
      ctx.shadowColor = strokeColor;
      ctx.shadowBlur = 4;

      const startX = 55;
      const plotWidth = width - startX - 10;
      const stepX = plotWidth / Math.max(1, activeSamples.length - 1);
      const scaleY = 55; // pixels per mV

      for (let i = 0; i < activeSamples.length; i++) {
        const x = startX + i * stepX;
        const val = activeSamples[i];
        const y = midY - val * scaleY;
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.shadowBlur = 0;
    } else {
      ctx.fillStyle = '#64748b';
      ctx.font = '12px Inter, sans-serif';
      ctx.fillText(
        inspectMode === 'HISTORICAL' ? 'No ECG samples at selected timestamp' : 'Awaiting ECG waveform stream...',
        width / 2 - 90,
        height / 2
      );
    }

    // Grid labels
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.fillText('Lead II (MLII) | 25 mm/s | 10 mm/mV', 60, 16);
    ctx.fillText(`${activeSamples.length} pts @ ${activeFs} Hz`, width - 130, 16);
  }, [activeSamples, activeFs, width, height, qualityStatus, inspectMode]);

  return (
    <div className="card space-y-2">
      {/* Header bar */}
      <div className="flex flex-wrap justify-between items-center gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <Activity className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Time-Aware ECG Waveform Explorer ({metadata?.channel_lead || 'Lead II'})
          </span>
          <span className="badge badge-purple">
            Record #{metadata?.patient_id || '100'} ({metadata?.is_synthetic ? 'Synthetic Fixture' : 'MIT-BIH Arrhythmia'})
          </span>
          <span className={`badge ${qualityStatus === 'ACCEPTABLE' ? 'badge-green' : 'badge-amber'}`}>
            SQI: {qualityStatus} ({snrDb} dB)
          </span>
          {inspectMode === 'HISTORICAL' && (
            <span className="badge badge-blue flex items-center gap-1">
              {isLoadingWindow ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              <span>Inspecting t = {targetTime.toFixed(2)}s</span>
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs">
          {inspectMode === 'HISTORICAL' ? (
            <button
              onClick={handleReturnToLive}
              className="btn btn-secondary text-[11px] py-0.5 px-2 flex items-center gap-1"
            >
              <RotateCcw className="w-3 h-3 text-emerald-400" />
              <span>Return to Live Stream</span>
            </button>
          ) : (
            <span className="text-[11px] text-slate-400 flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              {isReplay ? 'MIT-BIH Replay Stream' : 'Live Ingestion'}
            </span>
          )}
        </div>
      </div>

      {/* Canvas */}
      <div className="overflow-x-auto rounded border border-slate-800 bg-[#090d16]">
        <canvas ref={canvasRef} width={width} height={height} className="w-full h-auto block" />
      </div>

      {/* Time-Aware Navigation Controls */}
      <div className="bg-slate-950 p-2 rounded border border-slate-800/80 space-y-2 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          {/* Window step controls */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => handleStepWindow(false)}
              title="Previous window (-2s)"
              className="p-1 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => handleStepWindow(true)}
              title="Next window (+2s)"
              className="p-1 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
            <span className="text-slate-400 text-[11px] ml-1">Step Window</span>
          </div>

          {/* Time slider */}
          <div className="flex-1 flex items-center gap-2 min-w-[200px]">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <input
              type="range"
              min={0}
              max={Math.max(10, durationSec)}
              step={0.1}
              value={targetTime}
              onChange={(e) => handleTimeSliderChange(parseFloat(e.target.value))}
              className="flex-1 accent-sky-500 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
            />
            <span className="font-mono text-slate-300 text-[11px] w-12 text-right">
              {targetTime.toFixed(1)}s
            </span>
          </div>

          {/* Window width selector */}
          <div className="flex items-center gap-1 text-[11px] font-mono">
            <Sliders className="w-3 h-3 text-slate-400" />
            <span className="text-slate-400">Win:</span>
            {[1.0, 2.0, 5.0].map((w) => (
              <button
                key={w}
                onClick={() => {
                  setWindowSec(w);
                  fetchWindow(targetTime, w);
                }}
                className={`px-1.5 py-0.5 rounded transition ${
                  windowSec === w ? 'bg-sky-600 text-white font-semibold' : 'text-slate-400 hover:bg-slate-800'
                }`}
              >
                {w}s
              </button>
            ))}
          </div>
        </div>

        {/* Metadata display */}
        <div className="flex flex-wrap justify-between items-center text-[11px] text-slate-500 font-mono border-t border-slate-900 pt-1.5">
          <div>
            Range: 0.0s – {durationSec.toFixed(1)}s | FS: {activeFs} Hz | Lead: MLII
          </div>
          <div>
            {inspectMode === 'HISTORICAL' && inspectMetadata
              ? `Showing [${inspectMetadata.startTime.toFixed(2)}s - ${inspectMetadata.endTime.toFixed(2)}s] (${inspectMetadata.sampleCount} pts)`
              : `Live Buffer: ~${(activeSamples.length / activeFs).toFixed(2)}s`}
          </div>
        </div>
      </div>
    </div>
  );
};
