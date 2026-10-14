import React from 'react';
import type { RhythmPrediction } from '../types';
import { Brain, Cpu } from 'lucide-react';

interface RhythmDiagnosisCardProps {
  prediction?: RhythmPrediction | null;
  sqiStatus?: string;
  snrDb?: number;
}

export const RhythmDiagnosisCard: React.FC<RhythmDiagnosisCardProps> = ({
  prediction,
}) => {
  if (!prediction) {
    return (
      <div className="card space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-300">
          <Brain className="w-4 h-4 text-purple-400" />
          <span>Real-Time Rhythm AI Classifier</span>
        </div>
        <div className="text-xs text-slate-500 py-3 text-center">
          Analyzing beat windows for QRS complex...
        </div>
      </div>
    );
  }

  const isNormal = prediction.predicted_class === 'N';
  const isPVC = prediction.predicted_class === 'V';
  const isPAC = prediction.predicted_class === 'S';

  return (
    <div className="card space-y-2.5">
      <div className="flex justify-between items-center border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-purple-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Real-Time Rhythm AI Classifier
          </span>
        </div>
        <span className="text-[10px] font-mono text-slate-400">
          {prediction.model_version} ({prediction.inference_latency_ms.toFixed(1)}ms)
        </span>
      </div>

      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-xl font-bold font-mono tracking-tight flex items-center gap-2">
            <span
              className={
                isNormal
                  ? 'text-emerald-400'
                  : isPVC
                  ? 'text-rose-400'
                  : isPAC
                  ? 'text-amber-400'
                  : 'text-sky-400'
              }
            >
              Class [{prediction.predicted_class}]
            </span>
            <span className="text-xs font-normal text-slate-300">{prediction.class_label_meaning}</span>
          </div>
        </div>

        <span
          className={`badge ${
            isNormal ? 'badge-green' : isPVC ? 'badge-rose' : 'badge-amber'
          }`}
        >
          {isNormal ? 'NORMAL SINUS' : isPVC ? 'ECTOPIC BEAT' : 'SUPRAVENTRICULAR'}
        </span>
      </div>

      {/* Class Probabilities Bar Chart */}
      <div className="space-y-1 pt-1">
        <div className="flex justify-between text-[11px] text-slate-400 font-mono">
          <span>Uncalibrated Class Scores:</span>
          <span>(Random Forest Posteriori)</span>
        </div>
        <div className="grid grid-cols-5 gap-1.5 text-center font-mono text-[10px]">
          {Object.entries(prediction.class_scores).map(([cls, score]) => (
            <div key={cls} className="bg-slate-950 p-1.5 rounded border border-slate-800">
              <div className="text-slate-400 font-bold">{cls}</div>
              <div className="h-1.5 w-full bg-slate-800 rounded mt-1 overflow-hidden">
                <div
                  className={`h-full ${
                    cls === 'N' ? 'bg-emerald-500' : cls === 'V' ? 'bg-rose-500' : 'bg-amber-500'
                  }`}
                  style={{ width: `${Math.min(100, Math.max(0, score * 100))}%` }}
                ></div>
              </div>
              <div className="text-slate-300 mt-1">{(score * 100).toFixed(0)}%</div>
            </div>
          ))}
        </div>
      </div>

      {/* Scientific Semantic Disclaimer */}
      <div className="p-2 rounded bg-slate-950/80 border border-slate-800/80 text-[10px] text-slate-400 flex items-start gap-1.5">
        <Cpu className="w-3.5 h-3.5 text-purple-400 shrink-0 mt-0.5" />
        <span>
          <strong>Provenance:</strong> Patient-isolated trained classifier on MIT-BIH AAMI standards.
          Scores represent uncalibrated random forest leaf frequencies and do <em>not</em> claim future arrest prediction.
        </span>
      </div>
    </div>
  );
};
