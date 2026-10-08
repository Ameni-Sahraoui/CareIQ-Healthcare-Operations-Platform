# Data Dictionary

## Core governed entities

### PATIENT

Synthetic operational patient identifier and non-clinical access context: registration date, province, city, age band, preferred language, rurality, accessibility-support flag and digital-access level.

### FACILITY

Fictional network facility, province, city, facility type, timezone, operating model and nominal daily visit capacity.

### DEPARTMENT

Department/facility relationship, service group, slots, target wait, standard service duration and operating hours.

### PROVIDER

Synthetic provider identifier, department, operational role, employment status, FTE and capacity hours.

### APPOINTMENT

Patient, provider, department, facility, booking/scheduled time, appointment type, channel, attendance mode, operational priority, duration, reminder, status and rescheduling flag.

### WAIT_TIME

Arrival offset and queue components for registration, assessment, consultation and diagnostic/service, plus total wait and target-exceeded label.

### PATIENT_FLOW

Eight ordered operational stages: Appointment, Registration, Waiting, Assessment, Consultation, Diagnostic/Service, Treatment/Service completion and Discharge. Each row stores start, end, service duration and queue time.

### SATISFACTION

Synthetic service-experience survey scores and feedback category.

### CANCELLATION

Cancellation timestamp, hours before appointment, initiator, operational reason and 30-day rebooking flag.

### NO_SHOW

No-show recording time, confirmation status, outreach flag and non-clinical operational reason category.

### STAFFING

Department-day planned, actual and required hours, overtime, absence, agency hours and staffing-gap rate.

### SERVICE_EVENT

Operational event timestamp, type, category, resource, duration and exception flag.

## Analytical entities

### APPOINTMENT_FEATURE

Leakage-controlled historical/future appointment feature store. Protected demographic fields are retained for monitoring but excluded from the default predictive input list.

### DEPARTMENT_DAILY

Department-day demand, completion, no-show, cancellation, capacity, utilization, waiting statistics, satisfaction, staffing and pressure label.

### PREDICTION

Operational probability, risk band, lineage, explanatory factors, decision support and limitations.

### DEMAND_FORECAST

Daily department/type forecast with lower and upper uncertainty bounds and model lineage.

### GLOBAL_EXPLANATION and SEGMENT_EXPLANATION

Global and service-group model contribution summaries.

### DATA_QUALITY_RESULT

Validation result, severity, records checked, failures, status and details.

### DECISION_SUPPORT

Evidence, interpretation, operational suggestion and limitation. It contains no diagnosis or treatment guidance.
