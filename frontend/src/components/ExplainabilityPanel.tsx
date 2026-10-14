import React from 'react';
import { HelpCircle, Database, Cpu } from 'lucide-react';

export const ExplainabilityPanel: React.FC = () => {
  return (
    <div className="card space-y-3">
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <HelpCircle className="w-4 h-4 text-indigo-400" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Model Explainability & Provenance Architecture
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        {/* ML vs Rule-Based Distinction */}
        <div className="bg-slate-950 p-2.5 rounded border border-slate-800 space-y-1.5">
          <div className="flex items-center gap-1.5 text-indigo-300 font-semibold">
            <Cpu className="w-3.5 h-3.5" />
            <span>AI ML Classifier vs Rule-Based Fusion</span>
          </div>
          <p className="text-slate-400 text-[11px] leading-relaxed">
            <strong>ECG Classifier:</strong> Machine-learned Random Forest / Gaussian NB baseline operating on 16 beat-morphological and RR interval features. It evaluates uncalibrated class posteriors for AAMI categories (<code className="text-slate-200">N</code>, <code className="text-slate-200">V</code>, <code className="text-slate-200">S</code>).
          </p>
          <p className="text-slate-400 text-[11px] leading-relaxed">
            <strong>Late Fusion Engine:</strong> Deterministic, clinically validated National Early Warning Score (NEWS2) rules. Modalities are evaluated strictly by physiology guidelines, not aggregated by arbitrary black-box averaging.
          </p>
        </div>

        {/* Provenance & Synthetic Boundaries */}
        <div className="bg-slate-950 p-2.5 rounded border border-slate-800 space-y-1.5">
          <div className="flex items-center gap-1.5 text-emerald-300 font-semibold">
            <Database className="w-3.5 h-3.5" />
            <span>Data Provenance & Scientific Integrity</span>
          </div>
          <p className="text-slate-400 text-[11px] leading-relaxed">
            <strong>Observed ECG:</strong> Sourced from MIT-BIH Arrhythmia Database with ground-truth clinical annotations.
          </p>
          <p className="text-slate-400 text-[11px] leading-relaxed">
            <strong>Hemodynamics:</strong> Computed dynamically via Suga-Sagawa elastance ODEs and 2-element Windkessel compliance modeling. Clearly segregated from observed electrical waves.
          </p>
          <p className="text-amber-400/90 text-[10px]">
            * Zero cross-patient chimeric stitching. Missing data explicitly tagged STALE/MISSING.
          </p>
        </div>
      </div>
    </div>
  );
};
