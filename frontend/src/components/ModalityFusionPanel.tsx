import React from 'react';
import type { ModalityFreshness } from '../types';
import { Layers, CheckCircle2, Clock, XCircle } from 'lucide-react';

interface ModalityFusionPanelProps {
  freshnessMap: Record<string, ModalityFreshness>;
  riskScore: {
    news2_score: number;
    risk_category: 'LOW' | 'MEDIUM' | 'HIGH';
    evidence: Record<string, any>;
  };
}

export const ModalityFusionPanel: React.FC<ModalityFusionPanelProps> = ({
  freshnessMap,
  riskScore,
}) => {
  const getBadge = (status: 'FRESH' | 'STALE' | 'MISSING') => {
    switch (status) {
      case 'FRESH':
        return (
          <span className="badge badge-green flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Fresh
          </span>
        );
      case 'STALE':
        return (
          <span className="badge badge-amber flex items-center gap-1">
            <Clock className="w-3 h-3" /> Stale
          </span>
        );
      case 'MISSING':
      default:
        return (
          <span className="badge badge-rose flex items-center gap-1">
            <XCircle className="w-3 h-3" /> Missing
          </span>
        );
    }
  };

  const modalitiesList = [
    { key: 'ecg_chunk', name: 'ECG Continuous Waveform', expected: '< 2.5s' },
    { key: 'heart_rate', name: 'Instantaneous Heart Rate', expected: '< 5.0s' },
    { key: 'hrv_metrics', name: 'Derived HRV (RMSSD/SDNN)', expected: '< 10.0s' },
    { key: 'blood_pressure', name: 'Hemodynamic BP & SVR', expected: '< 15.0s' },
    { key: 'blood_glucose', name: 'Wearable Continuous Glucose', expected: '< 5.0m' },
    { key: 'ml_prediction', name: 'Rhythm ML Classification', expected: '< 5.0s' },
  ];

  return (
    <div className="card space-y-3">
      <div className="flex justify-between items-center border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-emerald-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Multimodal Ingestion & Freshness Matrix
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-400">NEWS2 Risk:</span>
          <span
            className={`badge font-mono font-bold ${
              riskScore.risk_category === 'HIGH'
                ? 'badge-rose'
                : riskScore.risk_category === 'MEDIUM'
                ? 'badge-amber'
                : 'badge-green'
            }`}
          >
            {riskScore.risk_category} ({riskScore.news2_score} pts)
          </span>
        </div>
      </div>

      <div className="divide-y divide-slate-800/80 text-xs">
        {modalitiesList.map((m) => {
          const f = freshnessMap[m.key] || {
            status: 'MISSING',
            age_seconds: 999,
            is_fresh: false,
          };
          return (
            <div key={m.key} className="py-1.5 flex justify-between items-center">
              <div>
                <span className="text-slate-300 font-medium block">{m.name}</span>
                <span className="text-[10px] text-slate-500 font-mono">
                  Tolerance: {m.expected} | Age: {f.age_seconds < 900 ? `${f.age_seconds.toFixed(1)}s` : 'N/A'}
                </span>
              </div>
              <div>{getBadge(f.status)}</div>
            </div>
          );
        })}
      </div>

      <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800 font-mono">
        Interpretable Late Fusion Rule: Missing modalities are marked UNKNOWN rather than hallucinated or backfilled with synthetic constants.
      </div>
    </div>
  );
};

