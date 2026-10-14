# Mathematical Lumped-Parameter Cardiovascular Simulation Model

**Module**: `backend/physiology.py` & `backend/scenarios.py`  
**Model Class**: `CardiovascularModel`  
**Classification**: Continuous ODE Lumped-Parameter Circulatory System  
**Intended Use**: Educational proof-of-concept, in-silico simulation research, and what-if physiological demonstrations.  
**Disclaimer**: **Not for medical diagnosis or clinical treatment.**

---

## 1. Model Overview and Mathematical Formulation

The simulation engine implements a time-varying elastance ventricular pump coupled with a multi-compartment Windkessel circulatory network. Rather than hardcoding sine waves or heuristic changing numbers, the system models the biophysical conservation of volume and pressure-flow relationships governed by coupled Ordinary Differential Equations (ODEs).

```
                      MITRAL VALVE (Diode)
        P_ven ---------------------> P_lv (Left Ventricle)
          ^                           |
          |                           |  AORTIC VALVE (Diode)
          |                           v
    C_ven (Venous Comp)           R_c (Aortic Impedance)
          ^                           |
          |                           v
          +<------- R_per <------- P_art (Arterial Tree, C_art)
             (Systemic Resistance)
```

### State Variables

| State Variable | Symbol | Dimension / Unit | Physiological Meaning |
| :--- | :--- | :--- | :--- |
| **Ventricular Volume** | $V_{\text{lv}}(t)$ | $\text{mL}$ | Left ventricular blood volume over the cardiac cycle |
| **Arterial Pressure** | $P_{\text{art}}(t)$ | $\text{mmHg}$ | Pressure in systemic large elastic arteries (Windkessel chamber) |
| **Venous Pressure** | $P_{\text{ven}}(t)$ | $\text{mmHg}$ | Pressure in the compliant systemic venous reservoir / left atrium |

---

## 2. Constitutive Equations & Hemodynamic Flows

### A. Time-Varying Ventricular Elastance ($E(t)$)
Based on the classic Suga & Sagawa double-hill elastance formulation:
$$P_{\text{lv}}(t) = E(t) \cdot (V_{\text{lv}}(t) - V_0)$$

Where $V_0$ is the volume at zero pressure ($\sim 15\text{ mL}$), and $E(t)$ varies periodically with cycle duration $T = 60 / \text{HR}$:
$$E(\tau) = E_{\text{min}} + (E_{\text{max}} - E_{\text{min}}) \cdot e_n(\tau)$$

$$\text{with } e_n(\tau) = \begin{cases} 
\frac{1}{2}\left[1 - \cos\left(\frac{\pi \tau}{T_{\text{sys}}}\right)\right] & 0 \le \tau \le T_{\text{sys}} \text{ (Systolic Contraction)} \\
\frac{1}{2}\left[1 + \cos\left(\frac{\pi (\tau - T_{\text{sys}})}{0.5 T_{\text{sys}}}\right)\right] & T_{\text{sys}} < \tau \le 1.5 T_{\text{sys}} \text{ (Diastolic Relaxation)} \\
0 & \text{otherwise (Diastasis)}
\end{cases}$$

### B. Cardiac Valve Flows
Valves are modeled as non-ideal hydraulic diodes with forward resistances:

*   **Mitral Valve Inflow** ($Q_{\text{in}}$):
    $$Q_{\text{in}}(t) = \begin{cases} \frac{P_{\text{ven}}(t) - P_{\text{lv}}(t)}{R_{\text{valv,in}}} & P_{\text{ven}} > P_{\text{lv}} \\ 0 & P_{\text{ven}} \le P_{\text{lv}} \end{cases}$$

*   **Aortic Valve Outflow** ($Q_{\text{out}}$):
    $$Q_{\text{out}}(t) = \begin{cases} \frac{P_{\text{lv}}(t) - P_{\text{art}}(t)}{R_{\text{valv,out}} + R_c} & P_{\text{lv}} > P_{\text{art}} \\ 0 & P_{\text{lv}} \le P_{\text{art}} \end{cases}$$

### C. Systemic Differential Equations (ODE System)

1. **Conservation of Ventricular Mass**:
   $$\frac{dV_{\text{lv}}}{dt} = Q_{\text{in}}(t) - Q_{\text{out}}(t)$$

2. **Arterial Chamber Pressure Dynamics**:
   $$\frac{dP_{\text{art}}}{dt} = \frac{Q_{\text{out}}(t) - Q_{\text{per}}(t)}{C_{\text{art}}}$$
   $$\text{where } Q_{\text{per}}(t) = \frac{P_{\text{art}}(t) - P_{\text{ven}}(t)}{R_{\text{per}}}$$

3. **Venous Compliance Pressure Dynamics**:
   $$\frac{dP_{\text{ven}}}{dt} = \frac{Q_{\text{per}}(t) - Q_{\text{in}}(t)}{C_{\text{ven}}}$$

---

## 3. Parameter Units, Nominal Values, and Physiological Ranges

| Parameter | Symbol | Nominal Value | Physiological Range | Standard Physical Unit | Clinical Meaning |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Heart Rate** | $\text{HR}$ | $75.0$ | $30.0 - 220.0$ | $\text{bpm}$ | Frequency of cardiac cycle |
| **End-Systolic Elastance** | $E_{\text{max}}$ | $2.00$ | $0.50 - 6.00$ | $\text{mmHg/mL}$ | Myocardial contractility (inotropy) |
| **End-Diastolic Elastance** | $E_{\text{min}}$ | $0.06$ | $0.01 - 0.30$ | $\text{mmHg/mL}$ | Diastolic ventricular stiffness |
| **Systolic Fraction** | $T_{\text{sys,ratio}}$ | $0.35$ | $0.20 - 0.50$ | dimensionless | Fraction of cycle spent in systole |
| **Unstressed Volume** | $V_0$ | $15.0$ | $5.0 - 30.0$ | $\text{mL}$ | Dead volume of left ventricle |
| **Aortic Impedance** | $R_c$ | $0.05$ | $0.01 - 0.25$ | $\text{mmHg}\cdot\text{s/mL}$ | Characteristic aortic root resistance |
| **Peripheral Resistance** | $R_{\text{per}}$ | $1.00$ | $0.20 - 4.00$ | $\text{mmHg}\cdot\text{s/mL}$ | Systemic vascular resistance (arterioles) |
| **Arterial Compliance** | $C_{\text{art}}$ | $1.20$ | $0.20 - 3.50$ | $\text{mL/mmHg}$ | Elastic capacitance of aorta/large vessels |
| **Venous Compliance** | $C_{\text{ven}}$ | $30.0$ | $5.0 - 100.0$ | $\text{mL/mmHg}$ | Capacitance of systemic venous reservoir |

---

## 4. Numerical Solver and Time Discretization

The engine provides two explicit time-stepping schemes:
1. **Runge-Kutta 4th Order (`rk4`, default)**:
   - Default integration time step: $\Delta t = 0.001\text{ s}$ ($1.0\text{ ms}$, $1,000\text{ Hz}$).
   - High numerical accuracy with fourth-order error scaling $\mathcal{O}(\Delta t^4)$.
2. **Forward Euler (`euler`)**:
   - For fast lightweight steps ($\Delta t = 0.0005\text{ s}$).

Numerical safeguards check for `NaN` and physical limits at every step ($V_{\text{lv}} \in [5, 350]\text{ mL}$, $P_{\text{art}} \in [10, 300]\text{ mmHg}$).

---

## 5. Integration With Observed ECG Signals

> [!IMPORTANT]
> **Separation of Observed vs Simulated Quantities**:
> - The ECG processor extracts electrical features (R-peaks, QRS complexes, arrhythmias like PVCs).
> - The physiological simulation engine calculates mechanical pressures, volumes, and flows ($P_{\text{art}}, V_{\text{lv}}, Q_{\text{out}}$).
> - While observed heart rate can drive the cycle length of the simulation ($T_{\text{cycle}} = 60 / \text{HR}$), **an ECG rhythm label does not arbitrarily overwrite hemodynamics without documented causal models**.
> - Observed ECG waveforms and simulated hemodynamic states remain distinct and separately traceable.

---

## 6. What-If Scenario Experiments (Validation & Results)

The engine provides reproducible what-if experiments via `ScenarioManager`. The model runs to a steady-state checkpoint, and both baseline and scenario branches run from identical initial conditions.

### Baseline vs Scenario Quantitative Results

| Experiment / Condition | Key Parameter Perturbations | Baseline CO | Scenario CO | Baseline SBP/DBP | Scenario SBP/DBP | Baseline EF | Scenario EF | Physiological Direction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Physical Exertion** | $\text{HR}: 75 \to 120\text{ bpm}$<br>$E_{\text{max}}: 2.0 \to 2.8$<br>$R_{\text{per}}: 1.0 \to 0.65$ | $4.92\text{ L/min}$ | **$8.23\text{ L/min}$** | $110.6 / 69.9$ | **$118.5 / 76.6$** | $47.5\%$ | **$53.3\%$** | Elevated cardiac output driven by chronotropy and inotropy with working muscle vasodilation. |
| **Beta-Blockade** (Metoprolol) | $\text{HR}: 75 \to 56\text{ bpm}$<br>$E_{\text{max}}: 2.0 \to 1.6$ | $4.92\text{ L/min}$ | **$3.93\text{ L/min}$** | $110.6 / 69.9$ | **$95.9 / 61.2$** | $47.5\%$ | **$47.8\%$** | Decreased heart rate and contractility reduce myocardial workload and arterial pressure. |
| **Arterial Vasodilation** (ACEi/CCB) | $R_{\text{per}}: 1.0 \to 0.68$ | $4.92\text{ L/min}$ | **$5.89\text{ L/min}$** | $110.6 / 69.9$ | **$99.4 / 62.7$** | $47.5\%$ | **$54.0\%$** | Reduced afterload lowers systemic blood pressure and facilitates ventricular emptying. |
| **Systolic Heart Failure** (HFrEF) | $E_{\text{max}}: 2.0 \to 0.85$<br>$\text{HR}: 75 \to 92\text{ bpm}$<br>$R_{\text{per}}: 1.0 \to 1.50$ | $4.92\text{ L/min}$ | **$2.46\text{ L/min}$** | $110.6 / 69.9$ | **$78.9 / 57.2$** | $47.5\%$ | **$18.6\%$** | Depressed contractility causes severe drop in EF ($<40\%$) and profound forward failure. |
| **Arterial Stiffening** (Aging) | $C_{\text{art}}: 1.2 \to 0.60$<br>$R_{\text{per}}: 1.0 \to 1.25$ | $4.92\text{ L/min}$ | **$4.17\text{ L/min}$** | $110.6 / 69.9$ | **$129.7 / 70.8$** | $47.5\%$ | **$40.5\%$** | Decreased arterial buffering causes high systolic peak and widened pulse pressure ($58.9\text{ mmHg}$). |

---

## 7. Model Assumptions and Known Limitations

1. **Lumped Parameter vs Distributed Flow**: Blood vessels are lumped into lumped compliances and resistances rather than distributed 1D Navier-Stokes transmission lines. Pulse wave reflections from bifurcations are approximated via the $R_c$ characteristic impedance.
2. **Left-Ventricle Isolation**: The current proof-of-concept models systemic left ventricular circulation. Pulmonary circulation and right ventricular interaction are held at constant venous preload ($P_{\text{ven}}$).
3. **Baroreceptor Reflex**: Parameter changes are evaluated in acute open-loop conditions without active neural baroreflex feedback.
4. **Arrhythmia Representation**: The hemodynamic model represents periodic cardiac cycles. Beat-to-beat chaotic arrhythmias (such as Atrial Fibrillation or Ventricular Fibrillation) must be driven beat-by-beat via observed $RR$ intervals from the ECG pipeline, rather than generated internally by this ODE model.

