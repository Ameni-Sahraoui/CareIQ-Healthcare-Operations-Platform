# Testing and QA

## Automated tests

The test suite verifies:

- required table presence and population
- SQLite integrity and foreign keys
- synthetic-data flags
- clean data-quality status
- eight-stage patient-flow coverage
- waiting-time reconciliation
- feature-store coverage and future-label protection
- comparison of Logistic Regression, Random Forest and XGBoost
- model-bundle completeness
- prediction coverage and probability bounds
- forecast horizon and interval validity
- explanation and decision-support presence
- non-clinical recommendation language
- consistency-audit status

Run:

```bash
pytest -q
```

## Consistency audit

The runtime audit traces:

`Patient → Appointment → Status → Wait/Flow/Survey → Features → Prediction → Explanation → Recommendation → Forecast → Dashboard export`

## Known validation limitation

The Streamlit UI is syntax-checked in the build environment. Browser-level visual testing should also be performed after installing Streamlit on the deployment machine.
