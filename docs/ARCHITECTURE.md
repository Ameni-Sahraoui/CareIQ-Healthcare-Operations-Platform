# CareIQ Architecture

## Scope

CareIQ is an operational intelligence system. It covers appointments, queues, staffing, capacity, demand and service experience. It excludes diagnosis, treatment recommendations, medication, clinical triage and any substitute for professional healthcare judgment.

## Layers

### 1. Synthetic source layer

`careiq.synthetic` creates a fictional Canadian network across six provinces. It generates internally related patients, facilities, departments, providers, appointments, staffing records, waiting times, eight-stage patient flows, service events, cancellations, no-shows and satisfaction surveys.

### 2. Data quality and governed storage

Transient anomalies are deliberately introduced into raw frames, recorded in `data/raw_samples/`, then repaired before loading the governed SQLite schema. `careiq.quality` validates keys, dates, duration ranges, status consistency, flow sequencing, synthetic flags and future-label leakage.

### 3. Feature stores

`APPOINTMENT_FEATURE` supports no-show, cancellation and waiting-risk models. It contains booking lead time, schedule context, patient operational history, reminder information, demand/utilization and staffing pressure.

`DEPARTMENT_DAILY` supports capacity analysis and forecasting. It contains demand, completion, no-shows, cancellations, capacity, waiting distributions, satisfaction, staffing gap and pressure labels.

Protected demographic fields are retained for monitoring but excluded from default model inputs.

### 4. Predictive analytics

Each classification task compares Logistic Regression, Random Forest and XGBoost using expanding temporal cross-validation and a later holdout. The selected model is persisted in `artifacts/model_bundle.joblib`.

### 5. Forecasting

A global department/appointment-type model compares seasonal naïve, histogram gradient boosting, random forest and XGBoost regression. Daily forecasts are recursively generated and include residual-based uncertainty intervals. Weekly and monthly views are aggregations of daily forecasts.

### 6. Explainability

Global and segment feature importance is generated from SHAP where applicable. Appointment predictions receive three high-contribution factors. Explanations describe model behaviour, not causal effects.

### 7. Decision support

`DECISION_SUPPORT` contains evidence, interpretation, operational suggestions and limitations. Suggestions are limited to non-clinical actions such as outreach, wait-list backfill, capacity review, staffing coverage, queue sequencing and schedule smoothing.

### 8. Presentation

The Streamlit application provides thirteen pages. Power BI-ready CSVs are exported from the governed database.

## Deployment topology

```text
Browser
  ↓
Streamlit application
  ↓
SQLite analytical database + joblib model bundle
  ↓
Python ETL / modeling / forecasting / explanation pipeline
```

For larger deployments, SQLite can be replaced with PostgreSQL while preserving the logical schema and exports.
