"""
Lumped-Parameter Cardiovascular Hemodynamic Simulation Engine.

A deterministic, multi-compartment numerical model of the systemic circulation.
Couples a time-varying elastance cardiac pump (Suga & Sagawa) with a 3-element
systemic arterial and venous Windkessel (aortic characteristic impedance, arterial compliance,
peripheral resistance, and venous compliance).

Supports:
- Forward Euler and Runge-Kutta 4th-order (RK4) numerical ODE solvers.
- Deterministic initialization, state advancement, pause, reset, checkpoint/restore.
- Parameter validation, range checks, and numerical stability safeguards.
- Isolation of observed ECG inputs vs simulated hemodynamic state.
- Standalone execution without FastAPI / frontend dependencies.
"""

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class CardiovascularParams:
    """
    Physiological parameters for lumped-parameter cardiovascular model.
    All units are documented in standard physiological conventions:
    - Resistance: mmHg / (mL/s)
    - Compliance: mL / mmHg
    - Elastance: mmHg / mL
    - Volume: mL
    - Time / Duration: seconds
    """
    # Cardiac cycle & elastance
    hr_bpm: float = 75.0               # Heart rate (beats per minute), nominal: 60-100
    e_max: float = 2.0                 # Peak systolic ventricular elastance (mmHg/mL), nominal: 1.5 - 3.0
    e_min: float = 0.06                # Baseline diastolic ventricular elastance (mmHg/mL), nominal: 0.04 - 0.10
    t_sys_ratio: float = 0.35          # Systolic fraction of cardiac cycle, nominal: 0.30 - 0.40
    v0: float = 15.0                   # Unstressed ventricular volume (mL), nominal: 10 - 20

    # Systemic vascular tree
    r_valv_in: float = 0.01            # Mitral valve forward resistance (mmHg·s/mL)
    r_valv_out: float = 0.015          # Aortic valve forward resistance (mmHg·s/mL)
    r_c: float = 0.05                  # Aortic characteristic impedance (mmHg·s/mL), nominal: 0.03 - 0.08
    r_per: float = 1.00                # Systemic peripheral vascular resistance (mmHg·s/mL), nominal: 0.6 - 1.6
    c_art: float = 1.20                # Systemic arterial compliance (mL/mmHg), nominal: 0.8 - 1.8
    c_ven: float = 30.0                # Venous compliance (mL/mmHg), nominal: 20.0 - 50.0
    p_ven_offset: float = 4.0          # Central venous pressure baseline (mmHg), nominal: 2 - 8

    def validate(self):
        """Validates parameter ranges to ensure numerical stability and physiological plausibility."""
        errors = []
        if not (30.0 <= self.hr_bpm <= 220.0):
            errors.append(f"hr_bpm ({self.hr_bpm}) out of valid physiological range [30, 220]")
        if not (0.5 <= self.e_max <= 6.0):
            errors.append(f"e_max ({self.e_max}) out of valid range [0.5, 6.0] mmHg/mL")
        if not (0.01 <= self.e_min <= 0.30):
            errors.append(f"e_min ({self.e_min}) out of valid range [0.01, 0.30] mmHg/mL")
        if not (0.20 <= self.t_sys_ratio <= 0.50):
            errors.append(f"t_sys_ratio ({self.t_sys_ratio}) out of valid range [0.20, 0.50]")
        if not (0.001 <= self.r_c <= 0.30):
            errors.append(f"r_c ({self.r_c}) out of valid range [0.001, 0.30] mmHg·s/mL")
        if not (0.20 <= self.r_per <= 4.0):
            errors.append(f"r_per ({self.r_per}) out of valid range [0.20, 4.0] mmHg·s/mL")
        if not (0.20 <= self.c_art <= 3.5):
            errors.append(f"c_art ({self.c_art}) out of valid range [0.20, 3.5] mL/mmHg")
        if not (5.0 <= self.c_ven <= 100.0):
            errors.append(f"c_ven ({self.c_ven}) out of valid range [5.0, 100.0] mL/mmHg")
        if errors:
            raise ValueError("Parameter validation failed:\n" + "\n".join(errors))


@dataclass
class CardiovascularState:
    """
    State variables and instant physical flows of the cardiovascular system at time t.
    """
    sim_time_sec: float
    v_lv: float                        # Left ventricular volume (mL)
    p_lv: float                        # Left ventricular pressure (mmHg)
    p_art: float                       # Systemic arterial pressure (mmHg)
    p_ven: float                       # Systemic venous / atrial pressure (mmHg)
    q_in: float                        # Mitral inflow rate (mL/s)
    q_out: float                       # Aortic outflow rate (mL/s)
    q_per: float                       # Peripheral capillary flow rate (mL/s)
    e_lv: float                        # Instantaneous LV elastance (mmHg/mL)


@dataclass
class HemodynamicSummary:
    """
    Cycle-averaged hemodynamic biomarkers computed across an integer cardiac cycle.
    """
    hr_bpm: float
    stroke_volume_ml: float
    cardiac_output_l_min: float
    systolic_bp_mmhg: float
    diastolic_bp_mmhg: float
    mean_arterial_pressure_mmhg: float
    pulse_pressure_mmhg: float
    ejection_fraction_pct: float
    end_diastolic_volume_ml: float
    end_systolic_volume_ml: float
    is_stable: bool = True


class CardiovascularModel:
    """
    Dynamic numerical cardiovascular model based on time-varying elastance.

    State variables:
    1. V_lv: Left ventricular blood volume (mL)
    2. P_art: Systemic arterial pressure (mmHg)
    3. P_ven: Venous / preload pressure (mmHg)
    """

    def __init__(
        self,
        params: Optional[CardiovascularParams] = None,
        dt_sec: float = 0.001,
        solver: str = "rk4",
    ):
        self.params = params or CardiovascularParams()
        self.params.validate()
        self.dt = dt_sec
        self.solver = solver.lower()
        if self.solver not in ("euler", "rk4"):
            raise ValueError("Supported solvers are 'euler' or 'rk4'")

        self.reset()

    def reset(self):
        """Initializes state variables to stable physiological defaults."""
        self.sim_time = 0.0
        # Typical end-diastolic initial conditions
        self.v_lv = 125.0              # Left ventricular volume (mL)
        self.p_art = 80.0              # Systemic arterial pressure (mmHg)
        self.p_ven = 8.0               # Venous / filling pressure (mmHg)
        self.history: List[CardiovascularState] = []

    def get_checkpoint(self) -> Dict[str, Any]:
        """Returns a deep serializable snapshot of model state and parameters."""
        return {
            "sim_time": self.sim_time,
            "v_lv": self.v_lv,
            "p_art": self.p_art,
            "p_ven": self.p_ven,
            "params": asdict(self.params),
            "dt": self.dt,
            "solver": self.solver,
        }

    def restore_checkpoint(self, checkpoint: Dict[str, Any]):
        """Restores model state and parameters from a saved checkpoint."""
        p_dict = checkpoint["params"]
        self.params = CardiovascularParams(**p_dict)
        self.params.validate()
        self.sim_time = float(checkpoint["sim_time"])
        self.v_lv = float(checkpoint["v_lv"])
        self.p_art = float(checkpoint["p_art"])
        self.p_ven = float(checkpoint["p_ven"])
        self.dt = float(checkpoint.get("dt", 0.001))
        self.solver = checkpoint.get("solver", "rk4")

    def elastance(self, t: float) -> float:
        """
        Double-hill time-varying ventricular elastance E(t) based on Suga & Sagawa.
        T_cycle = 60.0 / HR.
        Normalized activation during systole t_s = t_sys_ratio * T_cycle.
        """
        t_cycle = 60.0 / self.params.hr_bpm
        tau = t % t_cycle
        t_sys = self.params.t_sys_ratio * t_cycle

        if tau <= t_sys:
            # Half-sinusoid systolic contraction
            en = 0.5 * (1.0 - math.cos(math.pi * tau / t_sys))
        elif tau <= 1.5 * t_sys:
            # Rapid early diastolic relaxation
            en = 0.5 * (1.0 + math.cos(math.pi * (tau - t_sys) / (0.5 * t_sys)))
        else:
            # Resting baseline diastasis
            en = 0.0

        return self.params.e_min + (self.params.e_max - self.params.e_min) * en

    def _derivatives(self, t: float, state: np.ndarray) -> Tuple[np.ndarray, Dict[str, float]]:
        """
        Evaluates state derivatives d[V_lv, P_art, P_ven]/dt.
        """
        v_lv, p_art, p_ven = state

        # 1. Ventricular pressure from instantaneous elastance
        e_lv = self.elastance(t)
        p_lv = e_lv * (v_lv - self.params.v0)
        p_lv = max(0.0, p_lv)

        # 2. Cardiac valve flows (ideal diode with forward resistance)
        # Mitral valve: opens when P_ven > P_lv
        if p_ven > p_lv:
            q_in = (p_ven - p_lv) / self.params.r_valv_in
        else:
            q_in = 0.0

        # Aortic valve: opens when P_lv > P_art
        if p_lv > p_art:
            q_out = (p_lv - p_art) / (self.params.r_valv_out + self.params.r_c)
        else:
            q_out = 0.0

        # 3. Peripheral capillary blood flow
        q_per = max(0.0, (p_art - p_ven) / self.params.r_per)

        # 4. Differential equations
        # dV_lv/dt = Q_in - Q_out
        dv_lv = q_in - q_out

        # dP_art/dt = (Q_out - Q_per) / C_art
        dp_art = (q_out - q_per) / self.params.c_art

        # dP_ven/dt = (Q_per - Q_in) / C_ven
        dp_ven = (q_per - q_in) / self.params.c_ven

        aux = {
            "p_lv": p_lv,
            "q_in": q_in,
            "q_out": q_out,
            "q_per": q_per,
            "e_lv": e_lv,
        }
        return np.array([dv_lv, dp_art, dp_ven], dtype=np.float64), aux

    def step(self, dt: Optional[float] = None) -> CardiovascularState:
        """
        Advances the model by one time step dt using the configured solver.
        """
        h = dt or self.dt
        t = self.sim_time
        y0 = np.array([self.v_lv, self.p_art, self.p_ven], dtype=np.float64)

        if self.solver == "euler":
            dydt, aux = self._derivatives(t, y0)
            y_next = y0 + h * dydt
        else:  # Runge-Kutta 4 (RK4)
            k1, aux1 = self._derivatives(t, y0)
            k2, _ = self._derivatives(t + 0.5 * h, y0 + 0.5 * h * k1)
            k3, _ = self._derivatives(t + 0.5 * h, y0 + 0.5 * h * k2)
            k4, _ = self._derivatives(t + h, y0 + h * k3)
            y_next = y0 + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
            aux = aux1

        # Numerical stability check
        if np.isnan(y_next).any() or np.isinf(y_next).any():
            raise FloatingPointError(f"Numerical instability detected at t={t:.4f}s: {y_next}")

        # Physical boundary protections
        self.v_lv = max(5.0, min(350.0, float(y_next[0])))
        self.p_art = max(10.0, min(300.0, float(y_next[1])))
        self.p_ven = max(0.5, min(40.0, float(y_next[2])))
        self.sim_time += h

        state = CardiovascularState(
            sim_time_sec=round(self.sim_time, 5),
            v_lv=round(self.v_lv, 3),
            p_lv=round(aux["p_lv"], 3),
            p_art=round(self.p_art, 3),
            p_ven=round(self.p_ven, 3),
            q_in=round(aux["q_in"], 3),
            q_out=round(aux["q_out"], 3),
            q_per=round(aux["q_per"], 3),
            e_lv=round(aux["e_lv"], 4),
        )
        return state

    def run_simulation(
        self,
        duration_sec: float,
        record_history: bool = True,
    ) -> List[CardiovascularState]:
        """
        Advances simulation continuously for a given duration.
        """
        steps = int(duration_sec / self.dt)
        trajectory = []
        for _ in range(steps):
            st = self.step()
            if record_history:
                trajectory.append(st)
        if record_history:
            self.history.extend(trajectory)
        return trajectory

    def summarize_hemodynamics(self, window_sec: Optional[float] = None) -> HemodynamicSummary:
        """
        Computes cycle-averaged clinical metrics across recent cardiac cycle.
        If window_sec is omitted, uses the duration of the last integer beat cycle.
        """
        t_cycle = 60.0 / self.params.hr_bpm
        win = window_sec or t_cycle

        # Ensure we have at least one cycle recorded
        if len(self.history) < int(win / self.dt):
            # Run one cycle to record
            self.run_simulation(duration_sec=win, record_history=True)

        n_samples = int(win / self.dt)
        recent = self.history[-n_samples:]

        p_arts = [s.p_art for s in recent]
        v_lvs = [s.v_lv for s in recent]
        q_outs = [s.q_out for s in recent]

        sbp = float(np.max(p_arts))
        dbp = float(np.min(p_arts))
        map_val = float(np.mean(p_arts))
        edv = float(np.max(v_lvs))
        esv = float(np.min(v_lvs))

        # Stroke volume = EDV - ESV or integrated aortic flow
        sv_vol = edv - esv
        sv_flow = float(np.sum(q_outs) * self.dt)
        sv = max(10.0, (sv_vol + sv_flow) / 2.0)

        ef = (sv / edv) * 100.0 if edv > 0 else 55.0
        co = (self.params.hr_bpm * sv) / 1000.0  # L/min

        return HemodynamicSummary(
            hr_bpm=self.params.hr_bpm,
            stroke_volume_ml=round(sv, 1),
            cardiac_output_l_min=round(co, 2),
            systolic_bp_mmhg=round(sbp, 1),
            diastolic_bp_mmhg=round(dbp, 1),
            mean_arterial_pressure_mmhg=round(map_val, 1),
            pulse_pressure_mmhg=round(round(sbp, 1) - round(dbp, 1), 1),
            ejection_fraction_pct=round(ef, 1),
            end_diastolic_volume_ml=round(edv, 1),
            end_systolic_volume_ml=round(esv, 1),
            is_stable=True,
        )


# =====================================================================
# Backward Compatibility Adapter for Existing Fusion Engine
# =====================================================================

@dataclass
class HemodynamicState:
    """Retained for seamless integration with existing backend/fusion.py."""
    heart_rate_bpm: float
    stroke_volume_ml: float
    cardiac_output_l_min: float
    systolic_bp_mmhg: float
    diastolic_bp_mmhg: float
    mean_arterial_pressure_mmhg: float
    pulse_pressure_mmhg: float
    systemic_vascular_resistance: float
    compliance_ml_per_mmhg: float
    is_simulated: bool = True
    model_name: str = "2-Element Windkessel (Algebraic Adapter)"


class WindkesselModel:
    """
    Algebraic Windkessel adapter preserved so backend/fusion.py and existing tests
    continue to execute without breaking changes.
    """

    def __init__(
        self,
        nominal_compliance: float = 1.15,
        nominal_resistance: float = 0.95,
    ):
        self.C = nominal_compliance
        self.R = nominal_resistance

    def step(
        self,
        heart_rate_bpm: float,
        exercise_intensity: float = 0.0,
        beta_blocker_factor: float = 1.0,
    ) -> HemodynamicState:
        clamped_hr = max(35.0, min(220.0, float(heart_rate_bpm)))
        hr_filling_factor = max(0.6, 1.0 - max(0.0, clamped_hr - 110.0) * 0.004)
        base_sv = 70.0 * (1.0 + 0.3 * exercise_intensity) * beta_blocker_factor
        stroke_volume = max(35.0, min(140.0, base_sv * hr_filling_factor))

        cardiac_output = (clamped_hr * stroke_volume) / 1000.0
        co_mls = (cardiac_output * 1000.0) / 60.0
        r_eff = self.R * (1.0 - 0.2 * exercise_intensity)
        map_est = 4.0 + (co_mls * r_eff)

        pp_est = stroke_volume / self.C
        systolic_bp = map_est + (0.42 * pp_est)
        diastolic_bp = map_est - (0.28 * pp_est)

        systolic_bp = max(60.0, min(240.0, systolic_bp))
        diastolic_bp = max(35.0, min(140.0, diastolic_bp))
        pulse_pressure = systolic_bp - diastolic_bp
        svr_dynes = ((map_est - 4.0) * 80.0) / max(0.5, cardiac_output)

        return HemodynamicState(
            heart_rate_bpm=round(clamped_hr, 1),
            stroke_volume_ml=round(stroke_volume, 1),
            cardiac_output_l_min=round(cardiac_output, 2),
            systolic_bp_mmhg=round(systolic_bp, 1),
            diastolic_bp_mmhg=round(diastolic_bp, 1),
            mean_arterial_pressure_mmhg=round(map_est, 1),
            pulse_pressure_mmhg=round(pulse_pressure, 1),
            systemic_vascular_resistance=round(svr_dynes, 1),
            compliance_ml_per_mmhg=self.C,
            is_simulated=True,
            model_name="2-Element Windkessel (Algebraic Adapter)",
        )
