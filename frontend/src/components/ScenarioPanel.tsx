import React, { useState } from 'react';
import { ApiClient } from '../api';
import type { ScenarioComparisonResult, ScenarioDefinition } from '../types';
import { Play, RotateCcw, AlertTriangle } from 'lucide-react';

interface ScenarioPanelProps {
  presets: ScenarioDefinition[];
  onScenarioExecuted?: (result: ScenarioComparisonResult) => void;
}

export const ScenarioPanel: React.FC<ScenarioPanelProps> = ({ presets, onScenarioExecuted }) => {
  const [selectedPresetId, setSelectedPresetId] = useState<string>('exercise');
  const [customParams, setCustomParams] = useState<{
    hr_bpm: number;
    e_max: number;
    r_per: number;
    c_art: number;
  }>({
    hr_bpm: 85,
    e_max: 2.2,
    r_per: 0.9,
    c_art: 1.1,
  });
  const [isCustom, setIsCustom] = useState<boolean>(false);
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [result, setResult] = useState<ScenarioComparisonResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const selectedPreset = presets.find((p) => p.scenario_id === selectedPresetId);

  const handleRun = async () => {
    setIsRunning(true);
    setErrorMsg(null);
    try {
      let res: ScenarioComparisonResult;
      if (!isCustom) {
        res = await ApiClient.runScenario({
          scenario_id: selectedPresetId,
          duration_sec: 4.0,
        });
      } else {
        res = await ApiClient.runScenario({
          scenario_id: 'custom_experiment',
          title: 'Custom What-If Parameter Test',
          parameter_overrides: customParams,
          duration_sec: 4.0,
        });
      }
      setResult(res);
      if (onScenarioExecuted) onScenarioExecuted(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to execute scenario');
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="card space-y-3">
      <div className="flex justify-between items-center border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Cardiovascular What-If Simulation
          </span>
          <span className="badge badge-purple">In-Silico Research</span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setIsCustom(false)}
            className={`px-2 py-0.5 rounded transition ${
              !isCustom ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'
            }`}
          >
            Clinical Presets
          </button>
          <button
            onClick={() => setIsCustom(true)}
            className={`px-2 py-0.5 rounded transition ${
              isCustom ? 'bg-indigo-600 text-white font-medium' : 'text-slate-400 hover:text-white'
            }`}
          >
            Custom Knobs
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-2 rounded bg-rose-950/60 border border-rose-800 text-rose-200 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Preset Selector vs Custom Sliders */}
      {!isCustom ? (
        <div className="space-y-2">
          <div className="flex gap-2 flex-wrap">
            {presets.map((p) => (
              <button
                key={p.scenario_id}
                onClick={() => setSelectedPresetId(p.scenario_id)}
                className={`px-2.5 py-1 text-xs rounded border transition ${
                  selectedPresetId === p.scenario_id
                    ? 'border-indigo-500 bg-indigo-950/50 text-indigo-200 font-medium'
                    : 'border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700'
                }`}
              >
                {p.title}
              </button>
            ))}
          </div>

          {selectedPreset && (
            <div className="bg-slate-950/70 p-2.5 rounded border border-slate-800/80 text-xs space-y-1">
              <div className="text-slate-300 font-medium">{selectedPreset.description}</div>
              <div className="text-slate-400 italic">
                <strong>Hypothesis:</strong> {selectedPreset.physiological_hypothesis}
              </div>
              <div className="text-slate-500 font-mono text-[11px] pt-1">
                Overrides: {JSON.stringify(selectedPreset.parameter_overrides)}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <label className="text-slate-400 block mb-0.5">Heart Rate (HR): {customParams.hr_bpm} bpm</label>
            <input
              type="range"
              min={40}
              max={180}
              value={customParams.hr_bpm}
              onChange={(e) => setCustomParams({ ...customParams, hr_bpm: Number(e.target.value) })}
              className="w-full accent-indigo-500"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-0.5">Contractility (E_max): {customParams.e_max} mmHg/mL</label>
            <input
              type="range"
              min={0.6}
              max={4.0}
              step={0.1}
              value={customParams.e_max}
              onChange={(e) => setCustomParams({ ...customParams, e_max: Number(e.target.value) })}
              className="w-full accent-indigo-500"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-0.5">Peripheral Resistance: {customParams.r_per} mmHg·s/mL</label>
            <input
              type="range"
              min={0.4}
              max={2.5}
              step={0.05}
              value={customParams.r_per}
              onChange={(e) => setCustomParams({ ...customParams, r_per: Number(e.target.value) })}
              className="w-full accent-indigo-500"
            />
          </div>
          <div>
            <label className="text-slate-400 block mb-0.5">Arterial Compliance: {customParams.c_art} mL/mmHg</label>
            <input
              type="range"
              min={0.4}
              max={2.5}
              step={0.05}
              value={customParams.c_art}
              onChange={(e) => setCustomParams({ ...customParams, c_art: Number(e.target.value) })}
              className="w-full accent-indigo-500"
            />
          </div>
        </div>
      )}

      {/* Action CTA */}
      <div className="flex justify-between items-center pt-1">
        <button
          onClick={handleRun}
          disabled={isRunning}
          className="btn btn-primary flex items-center gap-1.5 text-xs"
        >
          {isRunning ? (
            <RotateCcw className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5 fill-current" />
          )}
          <span>{isRunning ? 'Integrating ODE Trajectory...' : 'Run What-If Comparison'}</span>
        </button>
        <span className="text-[11px] text-slate-500">Run length: 4.0s @ 1kHz RK4</span>
      </div>

      {/* Results Comparison Table */}
      {result && (
        <div className="mt-3 border-t border-slate-800 pt-3 space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-xs font-semibold text-slate-200">
              Comparative Hemodynamics: Baseline vs {result.title}
            </span>
            <span className="text-[10px] text-slate-400 font-mono">
              Delta: {result.duration_sec}s steady window
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] text-slate-400">
                  <th className="py-1">Biomarker</th>
                  <th className="py-1">Baseline</th>
                  <th className="py-1">Intervention</th>
                  <th className="py-1">Change (Δ)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                <tr>
                  <td className="py-1 text-slate-300">Cardiac Output (CO)</td>
                  <td className="py-1 text-slate-400">{result.baseline_summary.cardiac_output_l_min} L/min</td>
                  <td className="py-1 text-indigo-300 font-medium">{result.scenario_summary.cardiac_output_l_min} L/min</td>
                  <td className={`py-1 ${result.deltas.cardiac_output_l_min_delta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {result.deltas.cardiac_output_l_min_delta > 0 ? '+' : ''}{result.deltas.cardiac_output_l_min_delta} L/min
                  </td>
                </tr>
                <tr>
                  <td className="py-1 text-slate-300">Blood Pressure (SBP/DBP)</td>
                  <td className="py-1 text-slate-400">{result.baseline_summary.systolic_bp_mmhg} / {result.baseline_summary.diastolic_bp_mmhg}</td>
                  <td className="py-1 text-indigo-300 font-medium">{result.scenario_summary.systolic_bp_mmhg} / {result.scenario_summary.diastolic_bp_mmhg}</td>
                  <td className="py-1 text-slate-300">
                    Δ SBP: {result.deltas.systolic_bp_mmhg_delta > 0 ? '+' : ''}{result.deltas.systolic_bp_mmhg_delta} mmHg
                  </td>
                </tr>
                <tr>
                  <td className="py-1 text-slate-300">Ejection Fraction (EF)</td>
                  <td className="py-1 text-slate-400">{result.baseline_summary.ejection_fraction_pct} %</td>
                  <td className="py-1 text-indigo-300 font-medium">{result.scenario_summary.ejection_fraction_pct} %</td>
                  <td className={`py-1 ${result.deltas.ejection_fraction_pct_delta >= 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {result.deltas.ejection_fraction_pct_delta > 0 ? '+' : ''}{result.deltas.ejection_fraction_pct_delta} %
                  </td>
                </tr>
                <tr>
                  <td className="py-1 text-slate-300">Stroke Volume (SV)</td>
                  <td className="py-1 text-slate-400">{result.baseline_summary.stroke_volume_ml} mL</td>
                  <td className="py-1 text-indigo-300 font-medium">{result.scenario_summary.stroke_volume_ml} mL</td>
                  <td className="py-1 text-slate-300">
                    {result.deltas.stroke_volume_ml_delta > 0 ? '+' : ''}{result.deltas.stroke_volume_ml_delta} mL
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="p-2 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-400 flex items-start gap-1.5">
            <span className="text-amber-400 font-bold">DISCLAIMER:</span>
            <span>{result.disclaimer}</span>
          </div>
        </div>
      )}
    </div>
  );
};
