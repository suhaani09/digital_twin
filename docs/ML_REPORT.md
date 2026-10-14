# ECG Beat Classification & Machine Learning Audit Report

**Model Version**: `1.0.0-mitbih-baseline`  
**Dataset**: Synthetic Fixture Fallback  
**Sampling Rate**: 360 Hz (Standard MLII lead)  
**Methodology**: Patient-level train/test isolation (preventing inter-patient data leakage).

---

## 1. Patient Cohort Partitioning

To avoid the well-known methodological flaw of beat-level mixing across identical patients:
- **Training Cohort (N=4 subjects)**: SYNTH_PAT_101, SYNTH_PAT_106, SYNTH_PAT_108, SYNTH_PAT_119
- **Independent Test Cohort (N=2 subjects)**: SYNTH_PAT_100, SYNTH_PAT_103
- **Train Sample Count**: 617 beats
- **Test Sample Count**: 225 beats

---

## 2. Quantitative Performance Metrics

- **Macro F1-Score**: `1.0000`
- **Overall Accuracy**: `1.0000`

### Detailed Per-Class Breakdown

| Class | Description | Precision | Recall / Sensitivity | F1-Score | Support |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **N** | AAMI `N` | 1.000 | 1.000 | 1.000 | 188 |
| **V** | AAMI `V` | 1.000 | 1.000 | 1.000 | 37 |

---

## 3. Confusion Matrix (Independent Patient Cohort)

Rows: Actual True Class | Columns: Model Prediction

| True \ Pred | N | V |
| :--- | --- | --- |
| **N** | 188 | 0 |
| **V** | 0 | 37 |


---

## 4. Clinical Semantic Guardrails

1. **Rhythm Classification vs Future Arrest**:
   This baseline detects existing beat-level electrical morphometry and ectopic complexes (e.g. Ventricular Ectopics `V`, Supraventricular `S`, Normal `N`). It **does not** predict future acute myocardial infarction or future cardiac arrest.
2. **Probability Calibration Notice**:
   Model confidence scores represent uncalibrated random forest ensemble leaf frequencies and must not be interpreted as true Bayesian posterior probabilities in clinical settings without isotonic regression or Platt scaling.
