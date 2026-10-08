PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS FACILITY (
    facility_id TEXT PRIMARY KEY,
    facility_name TEXT NOT NULL,
    province TEXT NOT NULL,
    city TEXT NOT NULL,
    facility_type TEXT NOT NULL,
    timezone TEXT NOT NULL,
    operating_model TEXT NOT NULL,
    daily_visit_capacity INTEGER NOT NULL CHECK (daily_visit_capacity > 0),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1)
);

CREATE TABLE IF NOT EXISTS DEPARTMENT (
    department_id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    department_name TEXT NOT NULL,
    department_group TEXT NOT NULL,
    appointment_slots_daily INTEGER NOT NULL CHECK (appointment_slots_daily > 0),
    target_wait_minutes REAL NOT NULL CHECK (target_wait_minutes > 0),
    standard_service_minutes REAL NOT NULL CHECK (standard_service_minutes > 0),
    open_hour INTEGER NOT NULL CHECK (open_hour BETWEEN 0 AND 23),
    close_hour INTEGER NOT NULL CHECK (close_hour BETWEEN 1 AND 24),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (facility_id) REFERENCES FACILITY(facility_id)
);

CREATE TABLE IF NOT EXISTS PROVIDER (
    provider_id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    provider_role TEXT NOT NULL,
    employment_status TEXT NOT NULL,
    fte REAL NOT NULL CHECK (fte > 0 AND fte <= 1.5),
    weekly_capacity_hours REAL NOT NULL CHECK (weekly_capacity_hours > 0),
    years_in_network INTEGER NOT NULL CHECK (years_in_network >= 0),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (department_id) REFERENCES DEPARTMENT(department_id)
);

CREATE TABLE IF NOT EXISTS PATIENT (
    patient_id TEXT PRIMARY KEY,
    registration_date TEXT NOT NULL,
    province TEXT NOT NULL,
    city TEXT NOT NULL,
    age_band TEXT NOT NULL,
    preferred_language TEXT NOT NULL,
    rurality TEXT NOT NULL,
    accessibility_support_flag INTEGER NOT NULL CHECK (accessibility_support_flag IN (0,1)),
    digital_access_level TEXT NOT NULL,
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1)
);

CREATE TABLE IF NOT EXISTS APPOINTMENT (
    appointment_id TEXT PRIMARY KEY,
    patient_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    booked_at TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_type TEXT NOT NULL,
    booking_channel TEXT NOT NULL,
    attendance_mode TEXT NOT NULL,
    service_priority TEXT NOT NULL,
    planned_duration_minutes INTEGER NOT NULL CHECK (planned_duration_minutes > 0),
    reminder_sent INTEGER NOT NULL CHECK (reminder_sent IN (0,1)),
    reminder_channel TEXT,
    status TEXT NOT NULL CHECK (status IN ('Completed','No-Show','Cancelled','Scheduled')),
    rescheduled_flag INTEGER NOT NULL CHECK (rescheduled_flag IN (0,1)),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (patient_id) REFERENCES PATIENT(patient_id),
    FOREIGN KEY (department_id) REFERENCES DEPARTMENT(department_id),
    FOREIGN KEY (provider_id) REFERENCES PROVIDER(provider_id),
    FOREIGN KEY (facility_id) REFERENCES FACILITY(facility_id)
);

CREATE TABLE IF NOT EXISTS WAIT_TIME (
    wait_time_id TEXT PRIMARY KEY,
    appointment_id TEXT UNIQUE NOT NULL,
    arrival_offset_minutes REAL NOT NULL,
    registration_wait_minutes REAL NOT NULL CHECK (registration_wait_minutes >= 0),
    assessment_wait_minutes REAL NOT NULL CHECK (assessment_wait_minutes >= 0),
    consultation_wait_minutes REAL NOT NULL CHECK (consultation_wait_minutes >= 0),
    diagnostic_service_wait_minutes REAL NOT NULL CHECK (diagnostic_service_wait_minutes >= 0),
    total_wait_minutes REAL NOT NULL CHECK (total_wait_minutes >= 0),
    target_wait_minutes REAL NOT NULL CHECK (target_wait_minutes > 0),
    wait_target_exceeded INTEGER NOT NULL CHECK (wait_target_exceeded IN (0,1)),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (appointment_id) REFERENCES APPOINTMENT(appointment_id)
);

CREATE TABLE IF NOT EXISTS PATIENT_FLOW (
    flow_event_id TEXT PRIMARY KEY,
    appointment_id TEXT NOT NULL,
    stage_order INTEGER NOT NULL CHECK (stage_order BETWEEN 1 AND 8),
    stage_name TEXT NOT NULL,
    stage_start TEXT NOT NULL,
    stage_end TEXT NOT NULL,
    duration_minutes REAL NOT NULL CHECK (duration_minutes >= 0),
    queue_minutes REAL NOT NULL CHECK (queue_minutes >= 0),
    completed_flag INTEGER NOT NULL CHECK (completed_flag IN (0,1)),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (appointment_id) REFERENCES APPOINTMENT(appointment_id),
    UNIQUE (appointment_id, stage_order)
);

CREATE TABLE IF NOT EXISTS SATISFACTION (
    satisfaction_id TEXT PRIMARY KEY,
    appointment_id TEXT UNIQUE NOT NULL,
    survey_date TEXT NOT NULL,
    overall_score REAL NOT NULL CHECK (overall_score BETWEEN 1 AND 5),
    service_score REAL NOT NULL CHECK (service_score BETWEEN 1 AND 5),
    communication_score REAL NOT NULL CHECK (communication_score BETWEEN 1 AND 5),
    wait_experience_score REAL NOT NULL CHECK (wait_experience_score BETWEEN 1 AND 5),
    would_recommend INTEGER NOT NULL CHECK (would_recommend IN (0,1)),
    feedback_category TEXT NOT NULL,
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (appointment_id) REFERENCES APPOINTMENT(appointment_id)
);

CREATE TABLE IF NOT EXISTS CANCELLATION (
    cancellation_id TEXT PRIMARY KEY,
    appointment_id TEXT UNIQUE NOT NULL,
    cancelled_at TEXT NOT NULL,
    hours_before_appointment REAL NOT NULL CHECK (hours_before_appointment >= 0),
    cancelled_by TEXT NOT NULL,
    cancellation_reason TEXT NOT NULL,
    rebooked_within_30d INTEGER NOT NULL CHECK (rebooked_within_30d IN (0,1)),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (appointment_id) REFERENCES APPOINTMENT(appointment_id)
);

CREATE TABLE IF NOT EXISTS NO_SHOW (
    no_show_id TEXT PRIMARY KEY,
    appointment_id TEXT UNIQUE NOT NULL,
    recorded_at TEXT NOT NULL,
    confirmation_status TEXT NOT NULL,
    outreach_attempted INTEGER NOT NULL CHECK (outreach_attempted IN (0,1)),
    operational_reason_category TEXT NOT NULL,
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (appointment_id) REFERENCES APPOINTMENT(appointment_id)
);

CREATE TABLE IF NOT EXISTS STAFFING (
    staffing_id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    staffing_date TEXT NOT NULL,
    planned_hours REAL NOT NULL CHECK (planned_hours >= 0),
    actual_hours REAL NOT NULL CHECK (actual_hours >= 0),
    required_hours REAL NOT NULL CHECK (required_hours >= 0),
    overtime_hours REAL NOT NULL CHECK (overtime_hours >= 0),
    absence_hours REAL NOT NULL CHECK (absence_hours >= 0),
    agency_hours REAL NOT NULL CHECK (agency_hours >= 0),
    staffing_gap_rate REAL NOT NULL,
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (department_id) REFERENCES DEPARTMENT(department_id),
    UNIQUE (department_id, staffing_date)
);

CREATE TABLE IF NOT EXISTS SERVICE_EVENT (
    service_event_id TEXT PRIMARY KEY,
    appointment_id TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    operational_category TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    event_duration_minutes REAL NOT NULL CHECK (event_duration_minutes >= 0),
    exception_flag INTEGER NOT NULL CHECK (exception_flag IN (0,1)),
    synthetic_record INTEGER NOT NULL DEFAULT 1 CHECK (synthetic_record = 1),
    FOREIGN KEY (appointment_id) REFERENCES APPOINTMENT(appointment_id)
);

CREATE TABLE IF NOT EXISTS DATE_DIMENSION (
    date_key INTEGER PRIMARY KEY,
    full_date TEXT UNIQUE NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    week INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    is_weekend INTEGER NOT NULL,
    synthetic_holiday_flag INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS APPOINTMENT_FEATURE (
    appointment_id TEXT PRIMARY KEY,
    scheduled_at TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    patient_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    province TEXT NOT NULL,
    department_group TEXT NOT NULL,
    appointment_type TEXT NOT NULL,
    booking_channel TEXT NOT NULL,
    attendance_mode TEXT NOT NULL,
    service_priority TEXT NOT NULL,
    lead_days REAL NOT NULL,
    appointment_hour INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    month INTEGER NOT NULL,
    reminder_sent INTEGER NOT NULL,
    rescheduled_flag INTEGER NOT NULL,
    prior_appointments INTEGER NOT NULL,
    prior_no_shows INTEGER NOT NULL,
    prior_cancellations INTEGER NOT NULL,
    prior_attendance_rate REAL NOT NULL,
    days_since_prior_appointment REAL,
    department_daily_bookings INTEGER NOT NULL,
    department_capacity_slots INTEGER NOT NULL,
    utilization_ratio REAL NOT NULL,
    staffing_gap_rate REAL NOT NULL,
    overtime_rate REAL NOT NULL,
    planned_duration_minutes REAL NOT NULL,
    accessibility_support_flag INTEGER NOT NULL,
    rurality TEXT NOT NULL,
    age_band TEXT NOT NULL,
    no_show_label INTEGER,
    cancellation_label INTEGER,
    wait_risk_label INTEGER,
    total_wait_minutes REAL,
    target_wait_minutes REAL,
    feature_version TEXT NOT NULL,
    FOREIGN KEY (appointment_id) REFERENCES APPOINTMENT(appointment_id)
);

CREATE TABLE IF NOT EXISTS DEPARTMENT_DAILY (
    department_id TEXT NOT NULL,
    activity_date TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    province TEXT NOT NULL,
    department_group TEXT NOT NULL,
    scheduled_appointments INTEGER NOT NULL,
    completed_appointments INTEGER NOT NULL,
    no_shows INTEGER NOT NULL,
    cancellations INTEGER NOT NULL,
    capacity_slots INTEGER NOT NULL,
    utilization_ratio REAL NOT NULL,
    average_wait_minutes REAL,
    median_wait_minutes REAL,
    p90_wait_minutes REAL,
    satisfaction_score REAL,
    staffing_gap_rate REAL NOT NULL,
    overtime_hours REAL NOT NULL,
    capacity_pressure_label INTEGER NOT NULL,
    dataset_version TEXT NOT NULL,
    PRIMARY KEY (department_id, activity_date)
);

CREATE TABLE IF NOT EXISTS MODEL_REGISTRY (
    model_version TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    task_name TEXT NOT NULL,
    training_date TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    selected_flag INTEGER NOT NULL,
    feature_count INTEGER NOT NULL,
    temporal_train_end TEXT NOT NULL,
    temporal_test_start TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MODEL_METRIC (
    model_version TEXT NOT NULL,
    task_name TEXT NOT NULL,
    model_name TEXT NOT NULL,
    split_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    PRIMARY KEY (model_version, task_name, model_name, split_name, metric_name)
);

CREATE TABLE IF NOT EXISTS PREDICTION (
    prediction_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    task_name TEXT NOT NULL,
    probability REAL NOT NULL,
    risk_band TEXT NOT NULL,
    prediction_timestamp TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    top_factor_1 TEXT,
    top_factor_2 TEXT,
    top_factor_3 TEXT,
    decision_support TEXT NOT NULL,
    limitations TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DEMAND_FORECAST (
    forecast_id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    appointment_type TEXT NOT NULL,
    forecast_date TEXT NOT NULL,
    horizon_days INTEGER NOT NULL,
    forecast_count REAL NOT NULL CHECK (forecast_count >= 0),
    lower_bound REAL NOT NULL CHECK (lower_bound >= 0),
    upper_bound REAL NOT NULL CHECK (upper_bound >= 0),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    FOREIGN KEY (department_id) REFERENCES DEPARTMENT(department_id)
);

CREATE TABLE IF NOT EXISTS GLOBAL_EXPLANATION (
    explanation_id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    importance_value REAL NOT NULL,
    importance_rank INTEGER NOT NULL,
    explanation_type TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS SEGMENT_EXPLANATION (
    explanation_id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    segment_name TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    mean_abs_shap REAL NOT NULL,
    direction_text TEXT NOT NULL,
    model_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS MODEL_MONITORING (
    monitoring_id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    reference_value REAL,
    current_value REAL,
    drift_value REAL,
    status TEXT NOT NULL,
    measured_at TEXT NOT NULL,
    model_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DATA_QUALITY_RESULT (
    result_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    check_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    records_checked INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    status TEXT NOT NULL,
    details TEXT NOT NULL,
    checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS DECISION_SUPPORT (
    recommendation_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    recommendation_type TEXT NOT NULL,
    evidence TEXT NOT NULL,
    interpretation TEXT NOT NULL,
    operational_suggestion TEXT NOT NULL,
    limitation TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_appointment_date ON APPOINTMENT(appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointment_patient ON APPOINTMENT(patient_id, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_appointment_department ON APPOINTMENT(department_id, appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointment_status ON APPOINTMENT(status);
CREATE INDEX IF NOT EXISTS idx_flow_appointment ON PATIENT_FLOW(appointment_id, stage_order);
CREATE INDEX IF NOT EXISTS idx_staffing_department_date ON STAFFING(department_id, staffing_date);
CREATE INDEX IF NOT EXISTS idx_prediction_task_risk ON PREDICTION(task_name, risk_band, probability);
CREATE INDEX IF NOT EXISTS idx_forecast_department_date ON DEMAND_FORECAST(department_id, forecast_date);
