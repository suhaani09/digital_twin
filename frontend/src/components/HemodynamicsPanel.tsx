import React from 'react';
import type { HemodynamicState } from '../types';
import { HeartPulse } from 'lucide-react';

interface HemodynamicsPanelProps {
  hemodynamics?: HemodynamicState | null;
  hrBpm?: number | null;
  glucoseMgDl?: number | null;
}

export const HemodynamicsPanel: React.FC<HemodynamicsPanelProps> = ({
  hemodynamics,
  hrBpm,
  glucoseMgDl,
}) => {
  return (
    <div className="card space-y-3">
      <div className="flex justify-between items-center border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <HeartPulse className="w-4 h-4 text-rose-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Cardiovascular Digital Twin State
          </span>
        </div>
        <span className="badge badge-purple">
          {hemodynamics?.model_name || '2-Element Windkessel'}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        {/* Heart Rate */}
        <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block">Heart Rate</span>
          <div className="text-lg font-bold font-mono text-emerald-400">
            {hrBpm !== null && hrBpm !== undefined ? hrBpm.toFixed(0) : '--'}
            <span className="text-[10px] text-slate-500 font-normal ml-1">bpm</span>
          </div>
          <span className="text-[9px] text-slate-500">Nominal: 60 - 100</span>
        </div>

        {/* Blood Pressure */}
        <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block">Arterial BP</span>
          <div className="text-lg font-bold font-mono text-sky-400">
            {hemodynamics ? `${hemodynamics.systolic_bp_mmhg.toFixed(0)}/${hemodynamics.diastolic_bp_mmhg.toFixed(0)}` : '--/--'}
            <span className="text-[10px] text-slate-500 font-normal ml-1">mmHg</span>
          </div>
          <span className="text-[9px] text-slate-500">MAP: {hemodynamics ? `${hemodynamics.mean_arterial_pressure_mmhg.toFixed(0)} mmHg` : '--'}</span>
        </div>

        {/* Cardiac Output */}
        <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block">Cardiac Output</span>
          <div className="text-lg font-bold font-mono text-indigo-400">
            {hemodynamics ? hemodynamics.cardiac_output_l_min.toFixed(2) : '--'}
            <span className="text-[10px] text-slate-500 font-normal ml-1">L/min</span>
          </div>
          <span className="text-[9px] text-slate-500">SV: {hemodynamics ? `${hemodynamics.stroke_volume_ml.toFixed(1)} mL` : '--'}</span>
        </div>

        {/* Peripheral Resistance */}
        <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
          <span className="text-[10px] text-slate-400 uppercase tracking-wide block">Systemic Resistance</span>
          <div className="text-lg font-bold font-mono text-amber-400">
            {hemodynamics ? hemodynamics.systemic_vascular_resistance.toFixed(0) : '--'}
            <span className="text-[10px] text-slate-500 font-normal ml-1">dyn·s/cm⁵</span>
          </div>
          <span className="text-[9px] text-slate-500">Compliance: {hemodynamics?.compliance_ml_per_mmhg} mL/mmHg</span>
        </div>
      </div>

      {glucoseMgDl !== null && glucoseMgDl !== undefined && (
        <div className="bg-slate-950/60 p-2 rounded border border-slate-800 flex justify-between items-center text-xs">
          <span className="text-slate-400">Continuous Glucose (CGM):</span>
          <span className="font-mono font-semibold text-emerald-400">
            {glucoseMgDl.toFixed(1)} mg/dL
          </span>
        </div>
      )}
    </div>
  );
};
