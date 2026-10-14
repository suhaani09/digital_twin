"""
Reproducible Cardiovascular Simulation Demonstration.

Advances the lumped-parameter cardiovascular model over time,
runs comparative What-If experiments, and exports the state history to JSON.
"""

from dataclasses import asdict
import json
import os
import sys

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, os.path.abspath("."))

from backend.physiology import CardiovascularModel, CardiovascularParams
from backend.scenarios import PRESET_SCENARIOS, ScenarioManager


def run_demonstration(output_path: str = "docs/simulation_demo_output.json"):
    print("=====================================================================")
    print("CARDIOVASCULAR LUMPED-PARAMETER SIMULATION DEMONSTRATION")
    print("=====================================================================\n")

    # 1. Initialize Baseline Model
    params = CardiovascularParams(
        hr_bpm=75.0,
        e_max=2.0,
        r_per=1.00,
        c_art=1.20,
    )
    model = CardiovascularModel(params=params, dt_sec=0.001, solver="rk4")
    print(f"1. Initialized model with HR={params.hr_bpm} bpm, E_max={params.e_max} mmHg/mL, R_per={params.r_per} mmHg·s/mL, C_art={params.c_art} mL/mmHg")

    # 2. Advance 4.0 seconds to establish steady-state
    print("2. Advancing simulation by 4.0 seconds (4,000 RK4 integration steps)...")
    traj = model.run_simulation(duration_sec=4.0, record_history=True)
    baseline_summary = model.summarize_hemodynamics()

    print("\n   --- Baseline Steady-State Hemodynamics ---")
    print(f"   Heart Rate:               {baseline_summary.hr_bpm:.1f} bpm")
    print(f"   Blood Pressure (SBP/DBP): {baseline_summary.systolic_bp_mmhg:.1f} / {baseline_summary.diastolic_bp_mmhg:.1f} mmHg")
    print(f"   Mean Arterial Pressure:   {baseline_summary.mean_arterial_pressure_mmhg:.1f} mmHg")
    print(f"   Pulse Pressure:           {baseline_summary.pulse_pressure_mmhg:.1f} mmHg")
    print(f"   Stroke Volume:            {baseline_summary.stroke_volume_ml:.1f} mL")
    print(f"   Cardiac Output:           {baseline_summary.cardiac_output_l_min:.2f} L/min")
    print(f"   Ejection Fraction:        {baseline_summary.ejection_fraction_pct:.1f} %")
    print(f"   End-Diastolic Volume:     {baseline_summary.end_diastolic_volume_ml:.1f} mL")
    print(f"   End-Systolic Volume:      {baseline_summary.end_systolic_volume_ml:.1f} mL")

    # 3. Checkpoint state
    checkpoint = model.get_checkpoint()
    print("\n3. Saved steady-state checkpoint.")

    # 4. Run What-If Experiments via ScenarioManager
    print("\n4. Running What-If Experiments from identical baseline checkpoint:")
    sm = ScenarioManager(base_model=model)

    results = {}
    for scenario_key in ["exercise", "beta_blocker", "vasodilator", "heart_failure", "arterial_stiffening"]:
        exp = sm.run_experiment(scenario_input=scenario_key, duration_sec=4.0)
        results[scenario_key] = exp
        print(f"\n   Scenario [{exp.title}]:")
        print(f"   Hypothesis: {exp.hypothesis}")
        print(f"   Baseline CO: {exp.baseline_summary['cardiac_output_l_min']:.2f} L/min -> Scenario CO: {exp.scenario_summary['cardiac_output_l_min']:.2f} L/min (Delta: {exp.deltas['cardiac_output_l_min_delta']:+.2f} L/min)")
        print(f"   Baseline SBP: {exp.baseline_summary['systolic_bp_mmhg']:.1f} mmHg -> Scenario SBP: {exp.scenario_summary['systolic_bp_mmhg']:.1f} mmHg (Delta: {exp.deltas['systolic_bp_mmhg_delta']:+.1f} mmHg)")
        print(f"   Baseline EF:  {exp.baseline_summary['ejection_fraction_pct']:.1f}% -> Scenario EF:  {exp.scenario_summary['ejection_fraction_pct']:.1f}% (Delta: {exp.deltas['ejection_fraction_pct_delta']:+.1f}%)")

    # 5. Export history & results to JSON
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    export_payload = {
        "baseline_summary": asdict(baseline_summary),
        "scenarios": {k: asdict(v) for k, v in results.items()},
        "recent_trajectory_sample": [
            {
                "t": s.sim_time_sec,
                "p_art": s.p_art,
                "p_lv": s.p_lv,
                "v_lv": s.v_lv,
                "q_out": s.q_out,
            }
            for i, s in enumerate(traj[-800:])  # Last ~0.8s (1 cardiac cycle)
            if i % 10 == 0
        ],
    }
    with open(output_path, "w") as f:
        json.dump(export_payload, f, indent=2)

    print(f"\n5. Successfully exported full experiment history to {output_path}")
    print("=====================================================================")


if __name__ == "__main__":
    run_demonstration()

