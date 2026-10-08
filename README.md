# CareIQ — Healthcare Operations & Patient Experience Intelligence Platform

**From Healthcare Data to Better Operational Decisions.**

CareIQ is a complete synthetic healthcare-operations analytics prototype for capacity, appointment utilization, no-shows, cancellations, waiting time, patient flow, department pressure, demand forecasting and service experience.

> **Safety and scope notice:** CareIQ is not a medical diagnosis or treatment system. It never diagnoses disease, recommends treatment, prescribes medication or replaces healthcare professionals. All packaged records are fictional and synthetic, and they must never be represented as official Canadian healthcare statistics.

## Business scenario

The fictional CareIQ network operates facilities across Ontario, Quebec, Alberta, British Columbia, Manitoba and Saskatchewan. The platform helps administrators answer operational questions:

- Where are queues and hand-offs creating bottlenecks?
- Which upcoming appointments have elevated no-show, cancellation or waiting-time risk?
- Which departments are approaching capacity pressure?
- What demand is expected by department and appointment type?
- How do waiting time and service experience relate descriptively?
- What operational actions merit review, and what are the limitations of the evidence?

## Included application pages

1. Executive Overview
2. Patient Flow
3. Capacity
4. Demand Forecast
5. No-Show Risk
6. Waiting-Time Intelligence
7. Department Performance
8. Patient Experience
9. What-If Simulator
10. Model Lab
11. Data Quality
12. Responsible AI
13. Research Methodology

## End-to-end architecture

```text
Synthetic source generation
        ↓
Raw anomaly injection and validation
        ↓
Governed relational SQLite database
        ↓
Appointment and department-day feature stores
        ↓
Temporal model comparison
        ↓
No-show / cancellation / waiting / capacity predictions
        ↓
Demand forecasting + uncertainty intervals
        ↓
SHAP global, segment and individual explanations
        ↓
Transparent non-clinical decision support
        ↓
Monitoring, consistency audit and Power BI exports
        ↓
Streamlit operational application
```

## Relational entities

The governed database includes the required entities:

`PATIENT`, `APPOINTMENT`, `DEPARTMENT`, `PROVIDER`, `FACILITY`, `WAIT_TIME`, `PATIENT_FLOW`, `SATISFACTION`, `CANCELLATION`, `NO_SHOW`, `STAFFING`, and `SERVICE_EVENT`.

Analytical tables include `APPOINTMENT_FEATURE`, `DEPARTMENT_DAILY`, `MODEL_REGISTRY`, `MODEL_METRIC`, `PREDICTION`, `DEMAND_FORECAST`, `GLOBAL_EXPLANATION`, `SEGMENT_EXPLANATION`, `MODEL_MONITORING`, `DATA_QUALITY_RESULT`, and `DECISION_SUPPORT`.

## Models

Classification tasks compare:

- Logistic Regression
- Random Forest
- XGBoost

Tasks:

- Appointment no-show probability
- Appointment cancellation probability
- Waiting-time target-exceedance probability
- Department capacity-pressure probability

Evaluation includes temporal cross-validation and a later temporal holdout with ROC-AUC, PR-AUC, precision, recall, F1, Brier score and confusion-matrix counts. Decision thresholds are selected on a training-period calibration window, not on the final temporal holdout.

Demand forecasting compares:

- Seven-day seasonal naïve baseline
- Histogram Gradient Boosting
- Random Forest Regressor
- XGBoost Regressor

The forecast model uses date, seasonality, department/type identifiers, lag values and rolling demand. Evaluation reports MAE, RMSE, WAPE and empirical uncertainty-interval coverage.

## Quick start on Windows

Install Python 3.12, then open PowerShell inside the project folder:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

Open:

```text
http://localhost:8501
```

The packaged demonstration database, model bundle, forecasts and exports are already included. You do not need to rebuild them before opening the app.

## macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

## Docker

```bash
docker compose up --build
```

Open `http://localhost:8501`.

## Rebuild the synthetic demonstration

```bash
python -m careiq.bootstrap --mode demo
```

The synthetic generator is intentionally substantial because it builds appointment histories, staffing, eight-stage patient flows, service events and survey records. Rebuilding can take several minutes depending on hardware.

Generate the larger configuration:

```bash
python -m careiq.bootstrap --mode full
```

Custom scale:

```bash
python -m careiq.bootstrap --mode demo --patients 12000 --appointments 90000 --seed 123
```

## Run tests

```bash
pytest -q
```

## Power BI

CSV exports are under `exports/`. Recommended relationships and a suggested star-schema design are documented in `docs/POWER_BI.md`.

## Online deployment

For a portfolio deployment, push the repository to GitHub and deploy `app.py` through a Python/Streamlit host. Keep the packaged demonstration database and artifacts in the repository or place them on persistent storage. For controlled environments, use the included Dockerfile and mount `data/`, `artifacts/` and `exports/` as persistent volumes.

## Responsible-use rules

- Use only synthetic or lawfully de-identified operational data.
- Do not infer diagnosis, health status, treatment need or clinical priority.
- Do not automate denial of care, clinical triage, insurance decisions or staff discipline.
- Treat SHAP as model explanation, not causal evidence.
- Treat the what-if simulator as sensitivity analysis, not an intervention-effect estimate.
- Require human review, local validation, privacy assessment, fairness monitoring and operational governance before any real-world use.

## Research framing

**Research question:** How can predictive analytics and business intelligence improve healthcare operational decision-making while maintaining transparency, responsible AI and a strict non-clinical scope?

CareIQ connects business intelligence, predictive analytics, digital transformation, analytics capability, explainable AI and operational decision support. The project is designed as a reproducible research and portfolio artifact, not as a production medical device or clinical decision-support system.
