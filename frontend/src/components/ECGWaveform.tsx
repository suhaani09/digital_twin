import React, { useEffect, useRef } from 'react';

interface ECGWaveformProps {
  samples: number[];
  fs: number;
  width?: number;
  height?: number;
  qualityStatus?: string;
  snrDb?: number;
  isReplay?: boolean;
}

export const ECGWaveform: React.FC<ECGWaveformProps> = ({
  samples,
  fs = 360,
  width = 700,
  height = 180,
  qualityStatus = 'ACCEPTABLE',
  snrDb = 15.0,
  isReplay = false,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear background (clinical dark theme)
    ctx.fillStyle = '#090d16';
    ctx.fillRect(0, 0, width, height);

    // Draw clinical medical millimeter grid
    ctx.strokeStyle = '#162032';
    ctx.lineWidth = 1;
    const majorGrid = 25; // 0.2s major grid lines
    const minorGrid = 5;

    // Minor grid
    ctx.beginPath();
    ctx.strokeStyle = '#0f172a';
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

    // Draw calibration pulse indicator on left (1 mV = 10mm ~ 40px)
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
    if (samples.length > 1) {
      ctx.beginPath();
      // Waveform phosphor green for clean trace, amber if degraded
      const isClean = qualityStatus === 'ACCEPTABLE';
      ctx.strokeStyle = isClean ? '#10b981' : '#f59e0b';
      ctx.lineWidth = 2.0;
      ctx.shadowColor = isClean ? '#10b981' : '#f59e0b';
      ctx.shadowBlur = 4;

      const startX = 55;
      const plotWidth = width - startX - 10;
      const stepX = plotWidth / Math.max(1, samples.length - 1);

      // Scaling factor: typically ECG ranges -0.5 to 1.5 mV
      const scaleY = 55; // pixels per mV

      for (let i = 0; i < samples.length; i++) {
        const x = startX + i * stepX;
        const val = samples[i];
        const y = midY - val * scaleY;
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
      ctx.shadowBlur = 0; // reset shadow
    } else {
      // Empty / flatline indication
      ctx.fillStyle = '#64748b';
      ctx.font = '12px Inter, sans-serif';
      ctx.fillText('Awaiting ECG waveform stream...', width / 2 - 90, height / 2);
    }

    // Grid labels
    ctx.fillStyle = '#475569';
    ctx.font = '10px monospace';
    ctx.fillText('Lead II (MLII) | 25 mm/s | 10 mm/mV', 60, 16);
    ctx.fillText(`${samples.length} pts @ ${fs} Hz`, width - 110, 16);
  }, [samples, fs, width, height, qualityStatus]);

  return (
    <div className="card">
      <div className="flex justify-between items-center mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            ECG Continuous Waveform (Lead II)
          </span>
          <span className={`badge ${qualityStatus === 'ACCEPTABLE' ? 'badge-green' : 'badge-amber'}`}>
            SQI: {qualityStatus} ({snrDb} dB)
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>{isReplay ? 'Replay Source (MIT-BIH)' : 'Live Model Stream'}</span>
        </div>
      </div>

      <div className="overflow-x-auto rounded border border-slate-800 bg-[#090d16]">
        <canvas ref={canvasRef} width={width} height={height} className="w-full h-auto block" />
      </div>

      <div className="flex justify-between items-center mt-2 text-[11px] text-slate-500 font-mono">
        <div>Window: ~{(samples.length / fs).toFixed(2)}s | FS: {fs} Hz</div>
        <div>Scale: 1 mV = 10 mm | Time: 25 mm/s | Zero Phase Filtering: 0.5 - 45 Hz</div>
      </div>
    </div>
  );
};

