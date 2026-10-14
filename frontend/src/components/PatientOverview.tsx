import React from 'react';
import type { PatientContext } from '../types';
import { User } from 'lucide-react';

interface PatientOverviewProps {
  context: PatientContext;
  currentTimeSec: number;
}

export const PatientOverview: React.FC<PatientOverviewProps> = ({ context, currentTimeSec }) => {
  return (
    <div className="card space-y-2.5">
      <div className="flex justify-between items-center border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <User className="w-4 h-4 text-sky-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Patient Demographics & EHR Context
          </span>
        </div>
        <span className="badge badge-blue">
          ID: {context.patient_id} ({context.age || 58}y / {context.gender || 'M'})
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <span className="text-slate-400 block mb-1 font-medium">Diagnoses & History:</span>
          <div className="flex flex-wrap gap-1">
            {context.medical_history.map((h, i) => (
              <span key={i} className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 text-[11px]">
                {h}
              </span>
            ))}
          </div>
        </div>

        <div>
          <span className="text-slate-400 block mb-1 font-medium">Active Medications:</span>
          <div className="flex flex-wrap gap-1">
            {context.active_medications.map((m, i) => (
              <span key={i} className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-indigo-300 text-[11px]">
                {m}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="pt-1 flex justify-between items-center text-[11px] text-slate-500 font-mono">
        <div>Provenance: De-identified EHR Record & MIT-BIH Metadata</div>
        <div>Sim Time: {currentTimeSec.toFixed(2)}s</div>
      </div>
    </div>
  );
};
