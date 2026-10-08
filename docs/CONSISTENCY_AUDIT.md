# End-to-End Consistency Audit

Overall status: **PASS**

Passed: **37**  
Failed: **0**

| Check | Status | Value | Expectation |
|---|---|---|---|
| Required tables exist | PASS | 0 | Zero missing required tables |
| PATIENT populated | PASS | 8000 | More than zero rows |
| APPOINTMENT populated | PASS | 60000 | More than zero rows |
| DEPARTMENT populated | PASS | 60 | More than zero rows |
| PROVIDER populated | PASS | 201 | More than zero rows |
| FACILITY populated | PASS | 12 | More than zero rows |
| WAIT_TIME populated | PASS | 41196 | More than zero rows |
| PATIENT_FLOW populated | PASS | 329568 | More than zero rows |
| SATISFACTION populated | PASS | 27090 | More than zero rows |
| CANCELLATION populated | PASS | 9509 | More than zero rows |
| NO_SHOW populated | PASS | 7512 | More than zero rows |
| STAFFING populated | PASS | 56580 | More than zero rows |
| SERVICE_EVENT populated | PASS | 164784 | More than zero rows |
| APPOINTMENT_FEATURE populated | PASS | 60000 | More than zero rows |
| DEPARTMENT_DAILY populated | PASS | 56580 | More than zero rows |
| PREDICTION populated | PASS | 12549 | More than zero rows |
| DEMAND_FORECAST populated | PASS | 16200 | More than zero rows |
| MODEL_REGISTRY populated | PASS | 4 | More than zero rows |
| MODEL_METRIC populated | PASS | 228 | More than zero rows |
| DATA_QUALITY_RESULT populated | PASS | 39 | More than zero rows |
| DECISION_SUPPORT populated | PASS | 3846 | More than zero rows |
| Foreign-key integrity | PASS | 0 | Zero foreign-key violations |
| SQLite integrity | PASS | ok | ok |
| Synthetic-data labelling | PASS | 0 | Every record explicitly marked synthetic |
| Completed appointment to flow coverage | PASS | {"completed": 41196, "flow_appointments": 41196} | One flow record set per completed appointment |
| Eight-stage patient flow | PASS | 0 | Every completed flow has eight ordered stages |
| Wait-time reconciliation | PASS | 0 | Wait total equals components |
| Future prediction coverage: no_show | PASS | {"predictions": 1783, "future_appointments": 1783} | One prediction per future appointment |
| Future prediction coverage: cancellation | PASS | {"predictions": 1783, "future_appointments": 1783} | One prediction per future appointment |
| Future prediction coverage: wait_time_risk | PASS | {"predictions": 1783, "future_appointments": 1783} | One prediction per future appointment |
| Prediction probability range | PASS | 0 | All probabilities between 0 and 1 |
| Prediction lineage completeness | PASS | 0 | Model version, dataset version and timestamp populated |
| Forecast interval validity | PASS | 0 | Lower <= forecast <= upper and lower non-negative |
| Forecast horizon populated | PASS | 90 | At least 30 future daily forecast dates |
| High-risk decision-support coverage | PASS | {"high_risk": 3811, "recommendations": 3811} | At least one operational recommendation for each high-risk prediction |
| Post-clean data quality | PASS | 0 | Zero error-severity clean-data failures |
| Non-clinical recommendation boundary | PASS | 0 | No diagnosis, prescribing or medication language in operational suggestions |