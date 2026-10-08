# Power BI Integration

## Export location

Run:

```bash
python scripts/export_powerbi.py
```

Files are written to `exports/`.

## Suggested model

Dimensions:

- `date_dimension.csv`
- `facility.csv`
- `department.csv`
- `provider.csv`
- `patient.csv` for synthetic demonstration only

Facts:

- `appointment.csv`
- `wait_time.csv`
- `patient_flow.csv`
- `satisfaction.csv`
- `cancellation.csv`
- `no_show.csv`
- `staffing.csv`
- `service_event.csv`
- `department_daily.csv`
- `prediction.csv`
- `demand_forecast.csv`

## Recommended relationships

- Facility 1:* Department
- Department 1:* Provider
- Patient 1:* Appointment
- Department 1:* Appointment
- Provider 1:* Appointment
- Appointment 1:0..1 Wait Time
- Appointment 1:* Patient Flow
- Appointment 1:0..1 Satisfaction
- Appointment 1:0..1 Cancellation
- Appointment 1:0..1 No Show
- Department 1:* Staffing
- Department 1:* Department Daily
- Department 1:* Demand Forecast

## Measures

Suggested DAX measures include total appointments, completed visits, no-show rate, cancellation rate, average wait, median wait, P90 wait, utilization, pressure-day rate, satisfaction, forecast demand and forecast-capacity gap.

## Safety

Display a report-level notice that the dataset is fictional/synthetic and the report is operational, not clinical.
