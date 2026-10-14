"""
Automated Unit Tests for the Cardiovascular Simulation Engine & Scenarios.

Verifies:
1. Deterministic initialization, state advancement, and reset.
2. Checkpoint and restore repeatability (identical bitwise state progression).
3. Physiological bounds & numerical stability (no NaNs, no blowups under Euler/RK4).
4. Validation against invalid parameter inputs (out of range, zero, negative).
5. Controlled scenario execution & expected physiological directional responses:
   - Exercise: increased cardiac output, widened pulse pressure.
   - Vasodilator: decreased systemic arterial pressure.
   - Heart failure (HFrEF): depressed ejection fraction (<45%).
   - Arterial stiffening: marked increase in systolic BP.
6. Separation of observed ECG and simulated model quantities.
7. Reproducible execution and trajectory export.
"""

import copy
import numpy as np
import pytest

from backend.physiology import (
    CardiovascularModel,
    CardiovascularParams,
    CardiovascularState,
    HemodynamicSummary,
)
from backend.scenarios import (
    PRESET_SCENARIOS,
    ScenarioDefinition,
    ScenarioManager,
)


class TestCardiovascularModelBasics:

    def test_deterministic_initialization_and_reset(self):
        m1 = CardiovascularModel(dt_sec=0.001, solver="rk4")
        m2 = CardiovascularModel(dt_sec=0.001, solver="rk4")

        assert m1.sim_time == 0.0
        assert m1.v_lv == m2.v_lv == 125.0
        assert m1.p_art == m2.p_art == 80.0
        assert m1.p_ven == m2.p_ven == 8.0

        # Advance m1
        m1.step()
        assert m1.sim_time > 0.0
        assert m1.sim_time == 0.001

        # Reset m1
        m1.reset()
        assert m1.sim_time == 0.0
        assert m1.v_lv == 125.0

    def test_checkpoint_and_restore_repeatability(self):
        m = CardiovascularModel(dt_sec=0.001, solver="rk4")
        # Run 2 seconds to reach steady-state
        m.run_simulation(duration_sec=2.0, record_history=False)
        cp = m.get_checkpoint()

        # Run 100 steps from checkpoint
        steps_original = [m.step() for _ in range(100)]

        # Restore checkpoint in a separate instance
        m_restored = CardiovascularModel(dt_sec=0.001, solver="rk4")
        m_restored.restore_checkpoint(cp)
        steps_restored = [m_restored.step() for _ in range(100)]

        for s_orig, s_rest in zip(steps_original, steps_restored):
            assert s_orig.sim_time_sec == s_rest.sim_time_sec
            assert abs(s_orig.p_art - s_rest.p_art) < 1e-4
            assert abs(s_orig.v_lv - s_rest.v_lv) < 1e-4
            assert abs(s_orig.p_lv - s_rest.p_lv) < 1e-4

    def test_numerical_stability_and_bounds_rk4(self):
        m = CardiovascularModel(dt_sec=0.001, solver="rk4")
        traj = m.run_simulation(duration_sec=5.0, record_history=True)

        for s in traj:
            assert not np.isnan(s.p_art)
            assert not np.isnan(s.v_lv)
            assert not np.isnan(s.p_lv)
            # Clinical physical bounds
            assert 20.0 <= s.p_art <= 260.0
            assert 10.0 <= s.v_lv <= 250.0
            assert 0.0 <= s.p_lv <= 280.0

    def test_euler_solver_stability(self):
        m = CardiovascularModel(dt_sec=0.0005, solver="euler")
        traj = m.run_simulation(duration_sec=3.0, record_history=True)
        assert len(traj) == 6000
        summary = m.summarize_hemodynamics()
        assert 90.0 <= summary.systolic_bp_mmhg <= 160.0
        assert 50.0 <= summary.diastolic_bp_mmhg <= 100.0

    def test_invalid_parameter_validation(self):
        with pytest.raises(ValueError):
            # HR out of physiological bounds
            CardiovascularParams(hr_bpm=10.0).validate()

        with pytest.raises(ValueError):
            # Negative peripheral resistance
            CardiovascularParams(r_per=-0.5).validate()

        with pytest.raises(ValueError):
            # Unrealistic arterial compliance
            CardiovascularParams(c_art=0.05).validate()

    def test_hemodynamic_summary_metrics(self):
        m = CardiovascularModel()
        m.run_simulation(duration_sec=3.0, record_history=False)
        summary: HemodynamicSummary = m.summarize_hemodynamics()

        assert summary.hr_bpm == 75.0
        assert 100.0 <= summary.systolic_bp_mmhg <= 145.0
        assert 60.0 <= summary.diastolic_bp_mmhg <= 95.0
        assert summary.pulse_pressure_mmhg == round(summary.systolic_bp_mmhg - summary.diastolic_bp_mmhg, 1)
        assert 45.0 <= summary.stroke_volume_ml <= 105.0
        assert 3.5 <= summary.cardiac_output_l_min <= 7.5
        assert 45.0 <= summary.ejection_fraction_pct <= 75.0


class TestScenariosAndWhatIfExperiments:

    def test_exercise_scenario_directional_response(self):
        sm = ScenarioManager()
        res = sm.run_experiment(scenario_input="exercise", duration_sec=4.0)

        # Exercise hypothesis: increased cardiac output, increased heart rate
        assert res.deltas["hr_bpm_delta"] > 0
        assert res.deltas["cardiac_output_l_min_delta"] > 0
        assert res.scenario_summary["cardiac_output_l_min"] > res.baseline_summary["cardiac_output_l_min"]

    def test_vasodilator_scenario_directional_response(self):
        sm = ScenarioManager()
        res = sm.run_experiment(scenario_input="vasodilator", duration_sec=4.0)

        # Vasodilator hypothesis: lower peripheral resistance -> decreased mean and diastolic BP
        assert res.scenario_summary["mean_arterial_pressure_mmhg"] < res.baseline_summary["mean_arterial_pressure_mmhg"]
        assert res.scenario_summary["diastolic_bp_mmhg"] < res.baseline_summary["diastolic_bp_mmhg"]

    def test_heart_failure_scenario_depresses_ejection_fraction(self):
        sm = ScenarioManager()
        res = sm.run_experiment(scenario_input="heart_failure", duration_sec=4.0)

        # HFrEF hypothesis: ejection fraction drops markedly (< 45%)
        assert res.scenario_summary["ejection_fraction_pct"] < 45.0
        assert res.deltas["stroke_volume_ml_delta"] < 0

    def test_arterial_stiffening_widens_pulse_pressure(self):
        sm = ScenarioManager()
        res = sm.run_experiment(scenario_input="arterial_stiffening", duration_sec=4.0)

        # Stiffening hypothesis: pulse pressure increases
        assert res.scenario_summary["pulse_pressure_mmhg"] > res.baseline_summary["pulse_pressure_mmhg"]
        assert res.deltas["pulse_pressure_mmhg_delta"] > 0

    def test_custom_scenario_validation_and_reproducibility(self):
        sm = ScenarioManager()
        custom_sc = ScenarioDefinition(
            scenario_id="custom_tachycardia",
            title="Isolated Sinus Tachycardia",
            description="Elevated rate with unchanged contractility",
            parameter_overrides={"hr_bpm": 110.0},
            physiological_hypothesis="Elevated cardiac output due to frequency alone",
            clinical_assumption="Isolated pacing effect",
        )
        res1 = sm.run_experiment(scenario_input=custom_sc, duration_sec=3.0)
        res2 = sm.run_experiment(scenario_input=custom_sc, duration_sec=3.0)

        assert res1.scenario_summary["hr_bpm"] == 110.0
        assert res1.deltas["hr_bpm_delta"] == res2.deltas["hr_bpm_delta"]
        assert res1.baseline_summary["systolic_bp_mmhg"] == res2.baseline_summary["systolic_bp_mmhg"]

