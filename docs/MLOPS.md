# MLOps and Monitoring

## Lineage

Each selected model records:

- task name
- model family
- training timestamp
- dataset version
- temporal train end
- temporal holdout start
- feature count
- selected decision threshold

Each prediction records:

- task and entity
- probability and risk band
- prediction timestamp
- model version
- dataset version
- top model factors
- operational suggestion
- limitation

## Monitoring

`MODEL_MONITORING` contains feature population-stability indicators, current prediction distributions and forecast-interval width. Status values are informational, OK, WATCH or ALERT.

## Retraining triggers

A real implementation should define triggers based on:

- material PSI or distribution change
- deterioration in PR-AUC, recall or Brier score
- forecast WAPE and interval coverage
- group-level performance differences
- changes to appointment policy, capacity or staffing processes
- data-quality failure

## Versioning

The packaged bundle uses timestamped model and dataset versions. Do not overwrite a deployed model without preserving the prior artifact, metrics and approval record.
