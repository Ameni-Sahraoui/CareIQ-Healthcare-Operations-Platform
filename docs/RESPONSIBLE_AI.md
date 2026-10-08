# Responsible AI and Safety Boundary

## Visible use limitation

CareIQ is an operational analytics prototype. It is not a medical diagnostic or treatment system and must not replace healthcare professionals.

## Synthetic data

Every packaged operational record has `synthetic_record = 1`. Facility and network names are fictional. Province and city labels provide scenario context only. No output is an official Canadian healthcare statistic.

## Prohibited uses

CareIQ must not be used for:

- diagnosis or inference of disease
- treatment, medication or prescribing recommendations
- clinical triage or clinical-priority decisions
- denial or restriction of healthcare services
- insurance, employment or disciplinary decisions
- automated decisions without accountable human review
- re-identification or linkage of de-identified patients

## Appropriate use

The prototype can support research and operational review of appointment demand, queue management, capacity, reminders, wait-list processes, staffing pressure, patient flow and service experience.

## Fairness

Age band, language, rurality and accessibility indicators are excluded from the default predictive feature list. They remain available for group-level monitoring. Exclusion alone does not eliminate proxy discrimination, so error rates, calibration and operational impact must be evaluated across groups and facilities.

## Explainability

SHAP and coefficient contributions explain how the model arrived at a score. They do not demonstrate causation. A predictive feature should not automatically become an intervention target.

## Human oversight

Before operational action, users must inspect the evidence, limitations, data quality, local context and potential equity impact. Recommendations are prompts for review, not commands.

## What-if simulation

The simulator is a deterministic sensitivity model. It does not estimate causal effects of staffing, capacity or scheduling interventions.

## Monitoring

The packaged system records model versions, dataset versions, prediction timestamps, drift indicators, data-quality results and a consistency audit. Real deployments require ongoing performance monitoring, governance, security, privacy review and documented escalation processes.
