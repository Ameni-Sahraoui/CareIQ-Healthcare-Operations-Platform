# CareIQ Model Card

## Intended use

CareIQ models estimate non-clinical operational events: appointment no-show, cancellation, waiting-target exceedance, department capacity pressure and future appointment demand. They must not be used for diagnosis, treatment, medication, clinical triage or denial of service.

## Data

All training and evaluation data are synthetic. The demonstration contains 60,000 appointments and 8,000 fictional patients across six Canadian provinces. Metrics demonstrate pipeline behaviour only and do not establish real-world validity.

## Classification model comparison

Logistic Regression, Random Forest and XGBoost are compared using expanding temporal cross-validation. The selected model is then evaluated on a later temporal holdout. Decision thresholds are selected on a training-period calibration window.

| Task | Selected model | ROC-AUC | PR-AUC | Precision | Recall | F1 | Brier | Threshold |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| No Show | Logistic Regression | 0.573 | 0.161 | 0.136 | 0.881 | 0.235 | 0.262 | 0.44 |
| Cancellation | Logistic Regression | 0.651 | 0.324 | 0.382 | 0.359 | 0.370 | 0.227 | 0.53 |
| Wait Time Risk | XGBoost | 0.706 | 0.565 | 0.475 | 0.743 | 0.580 | 0.203 | 0.32 |
| Capacity Pressure | XGBoost | 0.883 | 0.469 | 0.353 | 0.713 | 0.472 | 0.070 | 0.19 |

## Demand forecast

Selected model: **HistGradientBoosting**. Daily department/type series are intentionally sparse, so daily WAPE is high; aggregation materially improves stability.

| Granularity | MAE | RMSE | WAPE |
|---|---:|---:|---:|
| Daily | 0.416 | 0.596 | 118.1% |
| Weekly | 1.159 | 1.538 | 49.3% |
| Monthly | 2.197 | 2.927 | 20.8% |

The temporal-holdout uncertainty interval achieved 90.0% empirical coverage. The interval is based on the 90th percentile of absolute residuals, not a complete probabilistic model.

## Explainability

Tree models use SHAP TreeExplainer with approximate evaluation; Logistic Regression uses signed linear contributions. Global, segment and appointment-level factors are stored. Explanations are model-behaviour descriptions, not causal evidence.

## Fairness design

Age band, rurality, preferred language and accessibility-support fields are excluded from default predictive features. Age band and rurality are retained for group-level calibration and error monitoring. Proxy discrimination can still occur.

## Limitations

- Synthetic performance cannot be generalized to a real healthcare network.
- No-show discrimination is modest in the demonstration and should be interpreted primarily as ranking, not certainty.
- Capacity pressure is partly constructed from utilization and staffing features, so its synthetic performance is not evidence of real deployment performance.
- Daily demand is sparse at department/type resolution; weekly and monthly views are more stable.
- The what-if simulator is sensitivity analysis, not causal inference.
- Predictions must remain subject to accountable human review.
