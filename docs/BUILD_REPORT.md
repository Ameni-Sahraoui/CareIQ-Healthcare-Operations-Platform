# CareIQ Build and Validation Report

## Delivered system

CareIQ is an executable healthcare-operations and patient-experience intelligence prototype with a synthetic generator, relational schema, ETL, feature stores, classification, forecasting, SHAP explanations, operational decision support, monitoring, a Streamlit application, Power BI exports, tests and Docker deployment files.

## Safety boundary

The system is explicitly non-clinical. It does not diagnose, recommend treatment, prescribe medication or replace healthcare professionals. Every packaged operational record is labelled synthetic, and the fictional network is not official Canadian healthcare data.

## Demonstration scale

| Entity | Rows |
|---|---:|
| Patient | 8,000 |
| Facility | 12 |
| Department | 60 |
| Provider | 201 |
| Appointment | 60,000 |
| Wait Time | 41,196 |
| Patient Flow | 329,568 |
| Satisfaction | 27,090 |
| Cancellation | 9,509 |
| No Show | 7,512 |
| Staffing | 56,580 |
| Service Event | 164,784 |
| Appointment Feature | 60,000 |
| Department Daily | 56,580 |
| Prediction | 12,549 |
| Demand Forecast | 16,200 |
| Decision Support | 3,846 |
| Global Explanation | 97 |
| Segment Explanation | 128 |
| Model Monitoring | 11 |

Database size: **147.5 MB** before ZIP compression.

## Selected models

| Task | Model | ROC-AUC | PR-AUC | Precision | Recall | F1 | Brier | Threshold |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| No Show | Logistic Regression | 0.573 | 0.161 | 0.136 | 0.881 | 0.235 | 0.262 | 0.44 |
| Cancellation | Logistic Regression | 0.651 | 0.324 | 0.382 | 0.359 | 0.370 | 0.227 | 0.53 |
| Wait Time Risk | XGBoost | 0.706 | 0.565 | 0.475 | 0.743 | 0.580 | 0.203 | 0.32 |
| Capacity Pressure | XGBoost | 0.883 | 0.469 | 0.353 | 0.713 | 0.472 | 0.070 | 0.19 |

## Forecast validation

The selected demand model is **HistGradientBoosting**. Daily, weekly and monthly holdout WAPE values are 118.1%, 49.3% and 20.8%. Holdout interval coverage is 90.0%. These are calculated values, not manually entered results.

## QA results

- Automated tests: **13 passed**
- End-to-end consistency audit: **37 passed, 0 failed**
- SQLite integrity: **OK**
- Foreign-key violations: **0**
- Error-severity clean-data quality failures: **0**
- Required future appointment prediction coverage: **100%** for no-show, cancellation and waiting risk
- Patient-flow sequence: **8 stages per completed appointment**

## Application validation

All Python modules and `app.py` passed syntax compilation. The data, feature, model, forecast, explanation, recommendation, monitoring, export and audit pipelines were executed. Streamlit was not installed in the build runtime, so browser rendering was not launched here; installing `requirements.txt` provides the UI runtime.

## Audit status

**PASS**
