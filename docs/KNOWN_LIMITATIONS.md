# Known Scientific, Clinical, and Engineering Limitations

**Status:** Documented for Research & Prototype Transparency  
**Target:** Hackathon Evaluators, Research Collaborators, and Peer Engineers

---

## 1. Clinical & Regulatory Disclaimers

> [!CAUTION]
> **NOT A CLINICAL DIAGNOSTIC TOOL**  
> This software is an experimental prototype created for academic research and hackathon demonstration. It is not approved by the FDA, CE, or any regulatory body. It must **never** be used for patient diagnosis, vital sign monitoring, triage, or clinical decision-making.

1. **No Real Patients Connected**: All signals are sourced from de-identified research archives (MIT-BIH Arrhythmia Database) or generated synthetic physiological fixtures.
2. **Hardware Disconnection**: No physical biomedical sensors (e.g. ECG electrodes, arterial lines, pulse oximeters) are interfaced with this software.

---

## 2. Machine-Learning Pipeline Limitations

1. **Rhythm Classification vs Event Prediction**:
   - The ML classifier detects existing beat-level morphometry within a single 200-sample window (-90 to +110 samples around R-peak) mapped to AAMI EC57 classes (`N`, `S`, `V`, `F`, `Q`).
   - It **does not** predict future acute myocardial infarctions, sudden cardiac arrest, or long-term cardiovascular mortality.
2. **Uncalibrated Model Confidence**:
   - Classification scores represent uncalibrated random forest leaf frequencies or naive Bayes log-likelihood posteriors.
   - They lack isotonic regression or Platt scaling calibration and must not be interpreted as Bayesian probabilities.
3. **Single Lead (MLII) Dependence**:
   - The current baseline is trained on single modified lead II (MLII) data. It lacks the 12-lead spatial vectorcardiographic information required to distinguish ischemia, axis deviations, or localized bundle branch blocks.

---

## 3. Physiological Simulation Model Limitations

1. **Lumped-Parameter Assumptions**:
   - The cardiovascular model is a 3-compartment lumped-parameter ODE system (left ventricle, systemic arterial tree, systemic venous compliance).
   - It lumps spatial wave propagation phenomena and arterial tree branching into a single compliance chamber ($C_{\text{art}}$) and peripheral resistance ($R_{\text{per}}$).
2. **Right-Heart & Pulmonary Exclusion**:
   - The right ventricle, pulmonary circulation, and pulmonary capillary wedge pressures are omitted in this proof-of-concept. Venous pressure $P_{\text{ven}}$ acts as an effective preload reservoir.
3. **Baroreflex Autonomic Control**:
   - The model does not include short-term closed-loop baroreceptor feedback mechanisms. In the current model, heart rate and contractility remain static unless perturbed by explicit what-if scenario overrides.
4. **Decoupling from ECG Rhythm**:
   - An abnormal rhythm classification (such as Ventricular Premature Contraction) does not automatically crash the simulation's blood pressure. Hemodynamic states change only according to the physical equations of the ODE model.

---

## 4. Engineering & Infrastructure Limitations

1. **In-Memory State Storage**:
   - Active digital twin sessions, circular buffers, and recent observations are stored in backend memory (`active_engines` dict). Restarting the FastAPI server clears session histories.
2. **Single-Node Scalability**:
   - WebSockets broadcast at 10 Hz from a single server instance. While efficient for demo sessions, enterprise-scale multi-patient deployment would require a distributed message broker (e.g. Redis Pub/Sub).
3. **Synthetic Dataset Fallback**:
   - When raw PhysioNet MIT-BIH `.dat` and `.hea` binaries are not downloaded locally, the pipeline seamlessly switches to synthetic ECG waveform fixtures. These fixtures allow full pipeline verification but do not capture clinical artifact variability.

