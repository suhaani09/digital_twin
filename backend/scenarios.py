"""
Cardiovascular What-If Experimentation Engine.

Provides a clean interface for controlled, reproducible physiological hypothesis testing:
- Checkpoints a baseline model state.
- Applies parameterized interventions (e.g. Dobutamine, Beta-blocker, Vasodilation, Hemorrhage).
- Runs baseline and intervention from identical initial conditions.
- Produces timestamped trajectory outputs and comparative summaries.
- Validates parameter limits and attaches clinical assumptions and disclaimers.
"""

from dataclasses import asdict, dataclass
import copy
from typing import Any, Dict, List, Optional
import numpy as np

from backend.physiology import (
    CardiovascularModel,
    CardiovascularParams,
    CardiovascularState,
    HemodynamicSummary,
)


@dataclass
class ScenarioDefinition:
    """Specification of an in-silico what-if experiment."""
    scenario_id: str
    title: str
    description: str
    parameter_overrides: Dict[str, float]
    physiological_hypothesis: str
    clinical_assumption: str


@dataclass
class ScenarioComparisonResult:
    """Comparative summary and time-series of baseline vs scenario run."""
    scenario_id: str
    title: str
    hypothesis: str
    duration_sec: float
    changed_parameters: Dict[str, Dict[str, float]]  # param -> {'baseline': X, 'scenario': Y}
    baseline_summary: Dict[str, Any]
    scenario_summary: Dict[str, Any]
    deltas: Dict[str, float]
    sample_trajectories: Dict[str, List[Dict[str, float]]]  # 'baseline' and 'scenario' time-series downsampled
    disclaimer: str


# Standard pre-configured physiological scenarios for education and demonstration
PRESET_SCENARIOS = {
    "exercise": ScenarioDefinition(
        scenario_id="exercise",
        title="Physical Exertion / Sympathetic Activation",
        description="Increases heart rate and cardiac contractility while reducing peripheral resistance.",
        parameter_overrides={
            "hr_bpm": 120.0,    # Elevated heart rate (bpm)
            "e_max": 2.8,       # Inotropic boost (mmHg/mL)
            "r_per": 0.65,      # Vasodilation in working skeletal muscle (mmHg·s/mL)
        },
        physiological_hypothesis="Elevated cardiac output driven by chronotropy and inotropy with moderate systolic rise and widened pulse pressure.",
        clinical_assumption="Standard healthy adult cardiovascular response during moderate aerobic activity.",
    ),
    "beta_blocker": ScenarioDefinition(
        scenario_id="beta_blocker",
        title="Beta-Adrenergic Blockade (e.g. Metoprolol)",
        description="Reduces sinus node automaticity (HR) and ventricular contractility (E_max).",
        parameter_overrides={
            "hr_bpm": 56.0,     # Decreased heart rate (bpm)
            "e_max": 1.6,       # Reduced myocardial contractility (mmHg/mL)
        },
        physiological_hypothesis="Reduction in myocardial oxygen demand, decreased cardiac output, and reduction in systolic arterial pressure.",
        clinical_assumption="Hypothetical therapeutic dosing response in resting posture.",
    ),
    "vasodilator": ScenarioDefinition(
        scenario_id="vasodilator",
        title="Arterial Vasodilation (e.g. ACE Inhibitor / CCB)",
        description="Reduces peripheral vascular resistance through systemic arteriolar relaxation.",
        parameter_overrides={
            "r_per": 0.68,      # Reduced afterload (mmHg·s/mL)
        },
        physiological_hypothesis="Significant drop in mean and diastolic arterial pressure with facilitated ventricular ejection.",
        clinical_assumption="Isolated vascular effect assuming baroreceptor reflex is blunted or reset.",
    ),
    "arterial_stiffening": ScenarioDefinition(
        scenario_id="arterial_stiffening",
        title="Isolated Systolic Hypertension / Aging Aorta",
        description="Decreases systemic arterial compliance (loss of aortic elasticity).",
        parameter_overrides={
            "c_art": 0.60,      # Stiffened aorta (mL/mmHg)
            "r_per": 1.25,      # Mild increase in systemic vascular resistance
        },
        physiological_hypothesis="Marked elevation in systolic blood pressure and wide pulse pressure due to reduced arterial buffering.",
        clinical_assumption="Typical geriatric cardiovascular remodeling in chronic isolated systolic hypertension.",
    ),
    "heart_failure": ScenarioDefinition(
        scenario_id="heart_failure",
        title="Systolic Heart Failure / Reduced Contractility (HFrEF)",
        description="Severe impairment of ventricular contractility with compensatory sympathetic vasoconstriction.",
        parameter_overrides={
            "e_max": 0.85,      # Severely diminished contractility (mmHg/mL)
            "hr_bpm": 92.0,     # Compensatory resting sinus tachycardia
            "r_per": 1.50,      # Compensatory peripheral vasoconstriction
        },
        physiological_hypothesis="Substantial decline in stroke volume and ejection fraction (<40%) with narrowed pulse pressure.",
        clinical_assumption="Simulated stage C heart failure with reduced ejection fraction.",
    ),
}


class ScenarioManager:
    """
    Executes and compares cardiovascular scenarios from reproducible checkpoints.
    """

    def __init__(self, base_model: Optional[CardiovascularModel] = None):
        self.base_model = base_model or CardiovascularModel()

    def get_preset_scenarios(self) -> List[Dict[str, Any]]:
        """Lists available educational scenario definitions."""
        return [asdict(sc) for sc in PRESET_SCENARIOS.values()]

    def run_experiment(
        self,
        scenario_input: Any,  # ScenarioDefinition or dict or str (preset id)
        duration_sec: float = 6.0,
        downsample_factor: int = 10,
    ) -> ScenarioComparisonResult:
        """
        Runs identical baseline and scenario simulations from the same steady-state checkpoint.
        """
        if isinstance(scenario_input, str):
            if scenario_input not in PRESET_SCENARIOS:
                raise ValueError(f"Unknown preset scenario '{scenario_input}'. Available: {list(PRESET_SCENARIOS.keys())}")
            sc_def = PRESET_SCENARIOS[scenario_input]
        elif isinstance(scenario_input, dict):
            sc_def = ScenarioDefinition(**scenario_input)
        else:
            sc_def = scenario_input

        # 1. Reach steady-state baseline (run 4 seconds)
        baseline_model = copy.deepcopy(self.base_model)
        baseline_model.reset()
        baseline_model.run_simulation(duration_sec=3.0, record_history=False)
        steady_checkpoint = baseline_model.get_checkpoint()

        # 2. Run Baseline trajectory from checkpoint
        baseline_run = copy.deepcopy(baseline_model)
        baseline_run.restore_checkpoint(steady_checkpoint)
        baseline_traj = baseline_run.run_simulation(duration_sec=duration_sec, record_history=True)
        baseline_sum = baseline_run.summarize_hemodynamics()

        # 3. Setup Scenario model with modified parameters from SAME checkpoint
        scenario_model = copy.deepcopy(baseline_model)
        scenario_model.restore_checkpoint(steady_checkpoint)

        changed_params: Dict[str, Dict[str, float]] = {}
        for param_name, new_val in sc_def.parameter_overrides.items():
            if not hasattr(scenario_model.params, param_name):
                raise ValueError(f"Unknown parameter override '{param_name}'")
            orig_val = getattr(scenario_model.params, param_name)
            setattr(scenario_model.params, param_name, float(new_val))
            changed_params[param_name] = {"baseline": orig_val, "scenario": float(new_val)}

        scenario_model.params.validate()

        # 4. Run Scenario trajectory
        # Allow 2 seconds of transition then evaluate steady-state window
        scenario_traj = scenario_model.run_simulation(duration_sec=duration_sec, record_history=True)
        scenario_sum = scenario_model.summarize_hemodynamics()

        # 5. Calculate Deltas
        deltas = {
            "hr_bpm_delta": round(scenario_sum.hr_bpm - baseline_sum.hr_bpm, 1),
            "stroke_volume_ml_delta": round(scenario_sum.stroke_volume_ml - baseline_sum.stroke_volume_ml, 1),
            "cardiac_output_l_min_delta": round(scenario_sum.cardiac_output_l_min - baseline_sum.cardiac_output_l_min, 2),
            "systolic_bp_mmhg_delta": round(scenario_sum.systolic_bp_mmhg - baseline_sum.systolic_bp_mmhg, 1),
            "diastolic_bp_mmhg_delta": round(scenario_sum.diastolic_bp_mmhg - baseline_sum.diastolic_bp_mmhg, 1),
            "pulse_pressure_mmhg_delta": round(scenario_sum.pulse_pressure_mmhg - baseline_sum.pulse_pressure_mmhg, 1),
            "ejection_fraction_pct_delta": round(scenario_sum.ejection_fraction_pct - baseline_sum.ejection_fraction_pct, 1),
        }

        # 6. Downsample time-series for compact, high-speed serialization
        def _downsample(traj: List[CardiovascularState]) -> List[Dict[str, float]]:
            return [
                {
                    "t": s.sim_time_sec,
                    "p_art": s.p_art,
                    "p_lv": s.p_lv,
                    "v_lv": s.v_lv,
                    "q_out": s.q_out,
                }
                for i, s in enumerate(traj)
                if i % downsample_factor == 0
            ]

        disclaimer = (
            "NOTICE: This is an in-silico mathematical simulation intended strictly for research and "
            "educational demonstration. It does NOT constitute medical advice, diagnosis, or clinical prediction."
        )

        return ScenarioComparisonResult(
            scenario_id=sc_def.scenario_id,
            title=sc_def.title,
            hypothesis=sc_def.physiological_hypothesis,
            duration_sec=duration_sec,
            changed_parameters=changed_params,
            baseline_summary=asdict(baseline_sum),
            scenario_summary=asdict(scenario_sum),
            deltas=deltas,
            sample_trajectories={
                "baseline": _downsample(baseline_traj),
                "scenario": _downsample(scenario_traj),
            },
            disclaimer=disclaimer,
        )

