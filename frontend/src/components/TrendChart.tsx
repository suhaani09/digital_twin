import React, { useEffect, useRef } from 'react';

interface TrendChartProps {
  title: string;
  unit: string;
  data: number[];
  timestamps?: number[];
  color?: string;
  minVal?: number;
  maxVal?: number;
  nominalRange?: [number, number];
  height?: number;
}

export const TrendChart: React.FC<TrendChartProps> = ({
  title,
  unit,
  data,
  color = '#38bdf8',
  minVal,
  maxVal,
  nominalRange,
  height = 90,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    // Background
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, w, h);

    if (data.length < 2) {
      ctx.fillStyle = '#475569';
      ctx.font = '11px sans-serif';
      ctx.fillText('Accumulating trend data...', 20, h / 2);
      return;
    }

    // Determine scale bounds
    const dataMin = Math.min(...data);
    const dataMax = Math.max(...data);
    const yMin = minVal !== undefined ? minVal : Math.max(0, dataMin * 0.9);
    const yMax = maxVal !== undefined ? maxVal : dataMax * 1.1 + 1;
    const yRange = yMax - yMin || 1;

    // Draw nominal green band if provided
    if (nominalRange) {
      const topY = h - ((nominalRange[1] - yMin) / yRange) * h;
      const botY = h - ((nominalRange[0] - yMin) / yRange) * h;
      ctx.fillStyle = 'rgba(16, 185, 129, 0.08)';
      ctx.fillRect(0, Math.max(0, topY), w, Math.max(0, botY - topY));
    }

    // Horizontal guideline
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();

    // Plot sparkline
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.0;
    ctx.beginPath();

    const stepX = w / (data.length - 1);
    data.forEach((val, i) => {
      const x = i * stepX;
      const y = h - ((val - yMin) / yRange) * (h - 10) - 5;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Area fill gradient
    const lastX = (data.length - 1) * stepX;
    ctx.lineTo(lastX, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = `${color}15`;
    ctx.fill();
  }, [data, color, minVal, maxVal, nominalRange]);

  const latestVal = data.length > 0 ? data[data.length - 1] : '--';

  return (
    <div className="bg-slate-900 border border-slate-800 rounded p-2.5">
      <div className="flex justify-between items-baseline mb-1">
        <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wide">{title}</span>
        <div className="text-right">
          <span className="text-base font-semibold font-mono" style={{ color }}>
            {typeof latestVal === 'number' ? latestVal.toFixed(1) : latestVal}
          </span>
          <span className="text-[10px] text-slate-500 ml-1">{unit}</span>
        </div>
      </div>
      <canvas ref={canvasRef} width={280} height={height} className="w-full h-auto block rounded" />
    </div>
  );
};

