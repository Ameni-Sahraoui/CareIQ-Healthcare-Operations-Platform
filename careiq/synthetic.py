from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

from careiq.config import GenerationConfig, RAW_SAMPLE_DIR
from careiq.database import connect, replace_table


PROVINCES = {
    "ON": {"cities": ["Toronto", "Ottawa", "Hamilton", "London"], "timezone": "America/Toronto", "weight": 0.25},
    "QC": {"cities": ["Montréal", "Québec City", "Laval", "Gatineau"], "timezone": "America/Toronto", "weight": 0.19},
    "AB": {"cities": ["Calgary", "Edmonton", "Red Deer", "Lethbridge"], "timezone": "America/Edmonton", "weight": 0.14},
    "BC": {"cities": ["Vancouver", "Victoria", "Surrey", "Kelowna"], "timezone": "America/Vancouver", "weight": 0.18},
    "MB": {"cities": ["Winnipeg", "Brandon", "Steinbach"], "timezone": "America/Winnipeg", "weight": 0.12},
    "SK": {"cities": ["Saskatoon", "Regina", "Moose Jaw"], "timezone": "America/Regina", "weight": 0.12},
}

DEPARTMENT_TEMPLATES = [
    {"name": "Primary Care Operations", "group": "Primary Care", "slots": (5, 11), "wait": 28, "service": 28, "types": ["Consultation", "Follow-up", "Virtual Consultation"]},
    {"name": "Diagnostic Services", "group": "Diagnostics", "slots": (4, 9), "wait": 35, "service": 38, "types": ["Diagnostic Service", "Follow-up", "Virtual Consultation"]},
    {"name": "Rehabilitation Services", "group": "Rehabilitation", "slots": (4, 8), "wait": 24, "service": 45, "types": ["Therapy Session", "Assessment", "Follow-up"]},
    {"name": "Specialty Clinic Operations", "group": "Specialty Clinics", "slots": (3, 8), "wait": 42, "service": 40, "types": ["Consultation", "Follow-up", "Procedure / Service"]},
    {"name": "Ambulatory Service Centre", "group": "Ambulatory Services", "slots": (3, 7), "wait": 38, "service": 52, "types": ["Procedure / Service", "Assessment", "Follow-up"]},
    {"name": "Virtual Care Hub", "group": "Virtual Care", "slots": (6, 14), "wait": 18, "service": 24, "types": ["Virtual Consultation", "Follow-up", "Assessment"]},
]

FACILITY_WORDS = [
    "Northlake", "Maple Ridge", "Prairie Sky", "Harbourview", "Northern Pines", "Riverstone",
    "Cedar Valley", "Aurora", "Lakeshore", "Summit", "Evergreen", "Grand River",
]

PROVIDER_ROLES = {
    "Primary Care": ["Physician", "Nurse Practitioner", "Registered Nurse"],
    "Diagnostics": ["Technologist", "Sonographer", "Registered Nurse"],
    "Rehabilitation": ["Physiotherapist", "Occupational Therapist", "Rehabilitation Assistant"],
    "Specialty Clinics": ["Specialist", "Registered Nurse", "Clinic Coordinator"],
    "Ambulatory Services": ["Proceduralist", "Registered Nurse", "Service Technician"],
    "Virtual Care": ["Physician", "Nurse Practitioner", "Virtual Care Coordinator"],
}

FLOW_STAGES = [
    "Appointment", "Registration", "Waiting", "Assessment", "Consultation",
    "Diagnostic/Service", "Treatment/Service completion", "Discharge",
]


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -20, 20)
    return 1.0 / (1.0 + np.exp(-clipped))


def _ids(prefix: str, count: int, width: int = 8) -> np.ndarray:
    return np.array([f"{prefix}{index:0{width}d}" for index in range(1, count + 1)], dtype=object)


def _date_dimension(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    synthetic_holiday = ((dates.month == 12) & (dates.day >= 24)) | ((dates.month == 1) & (dates.day <= 2))
    return pd.DataFrame(
        {
            "date_key": dates.strftime("%Y%m%d").astype(int),
            "full_date": dates.strftime("%Y-%m-%d"),
            "year": dates.year,
            "quarter": dates.quarter,
            "month": dates.month,
            "month_name": dates.month_name(),
            "week": dates.isocalendar().week.astype(int).to_numpy(),
            "day_of_week": dates.day_name(),
            "is_weekend": (dates.weekday >= 5).astype(int),
            "synthetic_holiday_flag": synthetic_holiday.astype(int),
        }
    )


def _build_facilities(config: GenerationConfig, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict] = []
    counter = 1
    for province, spec in PROVINCES.items():
        for local_index in range(config.facilities_per_province):
            city = spec["cities"][local_index % len(spec["cities"])]
            word = FACILITY_WORDS[(counter - 1) % len(FACILITY_WORDS)]
            facility_type = "Regional Ambulatory Centre" if local_index % 2 == 0 else "Community Health Centre"
            rows.append(
                {
                    "facility_id": f"F{counter:04d}",
                    "facility_name": f"{word} {facility_type} (Fictional)",
                    "province": province,
                    "city": city,
                    "facility_type": facility_type,
                    "timezone": spec["timezone"],
                    "operating_model": rng.choice(["Integrated", "Hub-and-spoke", "Community network"]),
                    "daily_visit_capacity": int(rng.integers(28, 70)),
                    "synthetic_record": 1,
                }
            )
            counter += 1
    return pd.DataFrame(rows)


def _build_departments(config: GenerationConfig, facilities: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict] = []
    counter = 1
    templates = DEPARTMENT_TEMPLATES[: config.departments_per_facility]
    for facility in facilities.itertuples(index=False):
        for template in templates:
            slots = int(rng.integers(template["slots"][0], template["slots"][1] + 1))
            rows.append(
                {
                    "department_id": f"D{counter:05d}",
                    "facility_id": facility.facility_id,
                    "department_name": template["name"],
                    "department_group": template["group"],
                    "appointment_slots_daily": slots,
                    "target_wait_minutes": float(template["wait"] + rng.integers(-4, 6)),
                    "standard_service_minutes": float(template["service"] + rng.integers(-5, 7)),
                    "open_hour": 7 if template["group"] != "Virtual Care" else 6,
                    "close_hour": 18 if template["group"] != "Virtual Care" else 21,
                    "synthetic_record": 1,
                }
            )
            counter += 1
    return pd.DataFrame(rows)


def _build_providers(departments: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rows: list[dict] = []
    counter = 1
    for department in departments.itertuples(index=False):
        provider_count = max(2, int(np.ceil(department.appointment_slots_daily / 2.2)))
        roles = PROVIDER_ROLES[department.department_group]
        for provider_index in range(provider_count):
            fte = float(rng.choice([0.5, 0.6, 0.8, 1.0, 1.0, 1.0]))
            rows.append(
                {
                    "provider_id": f"R{counter:06d}",
                    "department_id": department.department_id,
                    "provider_role": roles[provider_index % len(roles)],
                    "employment_status": "Permanent" if rng.random() < 0.84 else "Contract",
                    "fte": fte,
                    "weekly_capacity_hours": round(37.5 * fte, 1),
                    "years_in_network": int(rng.integers(0, 18)),
                    "synthetic_record": 1,
                }
            )
            counter += 1
    return pd.DataFrame(rows)


def _build_patients(config: GenerationConfig, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = config.n_patients
    province_codes = np.array(list(PROVINCES.keys()), dtype=object)
    weights = np.array([PROVINCES[p]["weight"] for p in province_codes], dtype=float)
    provinces = rng.choice(province_codes, size=n, p=weights / weights.sum())
    cities = np.array([rng.choice(PROVINCES[p]["cities"]) for p in provinces], dtype=object)
    start = pd.Timestamp(config.start_date)
    as_of = pd.Timestamp(config.as_of_date)
    registration_offsets = rng.integers(0, max(30, (as_of - start).days - 30), size=n)
    registration_dates = start + pd.to_timedelta(registration_offsets, unit="D")
    age_band = rng.choice(["0-17", "18-34", "35-49", "50-64", "65-74", "75+"], size=n, p=[0.11, 0.23, 0.22, 0.22, 0.13, 0.09])
    digital_level = rng.choice(["Low", "Moderate", "High"], size=n, p=[0.18, 0.43, 0.39])
    rurality = rng.choice(["Urban", "Suburban", "Rural"], size=n, p=[0.57, 0.27, 0.16])
    languages = np.array(["English", "French", "English/French", "Other"], dtype=object)
    language_prob = np.array([0.54, 0.23, 0.17, 0.06])
    preferred_language = rng.choice(languages, size=n, p=language_prob)
    reliability = rng.beta(6.0, 2.2, size=n)
    cancellation_tendency = rng.beta(1.8, 7.0, size=n)
    patients = pd.DataFrame(
        {
            "patient_id": _ids("P", n),
            "registration_date": registration_dates.strftime("%Y-%m-%d"),
            "province": provinces,
            "city": cities,
            "age_band": age_band,
            "preferred_language": preferred_language,
            "rurality": rurality,
            "accessibility_support_flag": (rng.random(n) < 0.12).astype(int),
            "digital_access_level": digital_level,
            "synthetic_record": 1,
        }
    )
    latent = pd.DataFrame(
        {
            "patient_id": patients["patient_id"],
            "reliability": reliability,
            "cancellation_tendency": cancellation_tendency,
            "registration_date": registration_dates,
            "province": provinces,
            "rurality": rurality,
            "digital_access_level": digital_level,
        }
    )
    return patients, latent


def _appointment_type_for_department(group: str, rng: np.random.Generator) -> str:
    template = next(item for item in DEPARTMENT_TEMPLATES if item["group"] == group)
    probabilities = np.array([0.50, 0.30, 0.20])
    return str(rng.choice(template["types"], p=probabilities))


def _build_appointments(
    config: GenerationConfig,
    patients: pd.DataFrame,
    latent: pd.DataFrame,
    facilities: pd.DataFrame,
    departments: pd.DataFrame,
    providers: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    n = config.n_appointments
    start = pd.Timestamp(config.start_date)
    end = pd.Timestamp(config.end_date)
    as_of = pd.Timestamp(config.as_of_date)
    dates = pd.date_range(start, end, freq="D")
    weekday_factor = np.array([1.16, 1.12, 1.06, 1.02, 0.86, 0.08, 0.05])[dates.weekday]
    month_factor_map = {1: 1.10, 2: 1.08, 3: 1.03, 4: 1.00, 5: 0.98, 6: 0.94, 7: 0.90, 8: 0.91, 9: 1.02, 10: 1.08, 11: 1.12, 12: 0.94}
    month_factor = np.array([month_factor_map[d.month] for d in dates])
    trend_factor = np.linspace(0.92, 1.10, len(dates))
    date_weights = weekday_factor * month_factor * trend_factor
    date_weights = date_weights / date_weights.sum()
    sampled_dates = pd.DatetimeIndex(rng.choice(dates.to_numpy(), size=n, p=date_weights))

    dept_weights = departments["appointment_slots_daily"].to_numpy(dtype=float)
    group_demand = departments["department_group"].map({
        "Primary Care": 1.18, "Diagnostics": 1.06, "Rehabilitation": 0.90,
        "Specialty Clinics": 1.02, "Ambulatory Services": 0.88, "Virtual Care": 1.12,
    }).to_numpy(dtype=float)
    dept_weights = dept_weights * group_demand
    dept_indexes = rng.choice(len(departments), size=n, p=dept_weights / dept_weights.sum())
    dept_rows = departments.iloc[dept_indexes].reset_index(drop=True)
    facility_lookup = facilities.set_index("facility_id")
    facility_rows = facility_lookup.loc[dept_rows["facility_id"]].reset_index()

    providers_by_dept = providers.groupby("department_id")["provider_id"].apply(list).to_dict()
    provider_ids = np.array([rng.choice(providers_by_dept[d]) for d in dept_rows["department_id"]], dtype=object)

    patient_indexes_by_province = {p: patients.index[patients["province"] == p].to_numpy() for p in PROVINCES}
    all_patient_indexes = patients.index.to_numpy()
    patient_indexes = np.empty(n, dtype=int)
    for province in PROVINCES:
        mask = facility_rows["province"].to_numpy() == province
        count = int(mask.sum())
        if count:
            local = patient_indexes_by_province[province]
            same_province = rng.random(count) < 0.91
            choices = rng.choice(local, size=count)
            choices[~same_province] = rng.choice(all_patient_indexes, size=int((~same_province).sum()))
            patient_indexes[mask] = choices
    patient_rows = patients.iloc[patient_indexes].reset_index(drop=True)
    latent_rows = latent.iloc[patient_indexes].reset_index(drop=True)

    appointment_types = np.array([_appointment_type_for_department(g, rng) for g in dept_rows["department_group"]], dtype=object)
    attendance_mode = np.where(
        np.isin(appointment_types, ["Virtual Consultation"]),
        "Virtual",
        np.where((dept_rows["department_group"].to_numpy() == "Virtual Care") & (rng.random(n) < 0.82), "Virtual", "In-person"),
    )
    hours = np.empty(n, dtype=int)
    for idx, row in enumerate(dept_rows.itertuples(index=False)):
        hour_values = np.arange(row.open_hour, row.close_hour)
        center = 10.5 if row.department_group != "Virtual Care" else 13.0
        hour_weights = np.exp(-0.5 * ((hour_values - center) / 3.0) ** 2) + 0.12
        hours[idx] = int(rng.choice(hour_values, p=hour_weights / hour_weights.sum()))
    minutes = rng.choice([0, 10, 20, 30, 40, 50], size=n)
    scheduled_at = sampled_dates + pd.to_timedelta(hours, unit="h") + pd.to_timedelta(minutes, unit="m")

    base_lead = np.where(np.isin(appointment_types, ["Diagnostic Service", "Procedure / Service"]), 28, 14)
    lead_days = np.maximum(0, np.round(rng.gamma(shape=1.8, scale=base_lead / 1.8, size=n))).astype(int)
    lead_days = np.clip(lead_days, 0, 120)
    booked_at = scheduled_at - pd.to_timedelta(lead_days, unit="D") - pd.to_timedelta(rng.integers(0, 10, size=n), unit="h")
    registration = pd.to_datetime(patient_rows["registration_date"])
    too_early = booked_at < registration
    booked_at = pd.Series(booked_at)
    booked_at.loc[too_early] = registration.loc[too_early] + pd.to_timedelta(rng.integers(0, 48, size=int(too_early.sum())), unit="h")
    scheduled_at = pd.Series(scheduled_at)
    invalid_after_adjust = booked_at >= scheduled_at
    booked_at.loc[invalid_after_adjust] = scheduled_at.loc[invalid_after_adjust] - pd.to_timedelta(1, unit="h")

    booking_channel = rng.choice(["Portal", "Phone", "Referral", "Front Desk", "Mobile"], size=n, p=[0.31, 0.27, 0.20, 0.12, 0.10])
    reminder_probability = np.where(patient_rows["digital_access_level"].to_numpy() == "High", 0.94, np.where(patient_rows["digital_access_level"].to_numpy() == "Moderate", 0.84, 0.64))
    reminder_sent = (rng.random(n) < reminder_probability).astype(int)
    reminder_channel = np.where(reminder_sent == 0, None, np.where(patient_rows["digital_access_level"].to_numpy() == "Low", "Automated Call", rng.choice(["SMS", "Email", "Portal"], size=n, p=[0.58, 0.23, 0.19])))
    service_priority = rng.choice(["Routine", "Priority", "Time-sensitive"], size=n, p=[0.72, 0.22, 0.06])
    planned_duration = dept_rows["standard_service_minutes"].to_numpy() * rng.normal(1.0, 0.12, size=n)
    planned_duration = np.maximum(10, np.round(planned_duration / 5) * 5).astype(int)

    is_historical = sampled_dates <= as_of
    digital_low = (patient_rows["digital_access_level"].to_numpy() == "Low").astype(float)
    rural = (patient_rows["rurality"].to_numpy() == "Rural").astype(float)
    late_day = (hours >= 16).astype(float)
    virtual = (attendance_mode == "Virtual").astype(float)
    reminder_missing = 1 - reminder_sent
    no_show_logit = -2.65 + 0.012 * lead_days + 1.25 * (1 - latent_rows["reliability"].to_numpy()) + 0.34 * rural + 0.42 * reminder_missing + 0.20 * late_day - 0.28 * virtual + 0.18 * (booking_channel == "Phone")
    no_show_probability = np.clip(_sigmoid(no_show_logit), 0.015, 0.38)
    cancel_logit = -2.25 + 0.010 * lead_days + 1.8 * latent_rows["cancellation_tendency"].to_numpy() + 0.22 * digital_low + 0.22 * (service_priority == "Routine") + 0.18 * (booking_channel == "Phone")
    cancellation_probability = np.clip(_sigmoid(cancel_logit), 0.025, 0.42)
    random_no_show = rng.random(n)
    random_cancel = rng.random(n)
    status = np.full(n, "Scheduled", dtype=object)
    no_show_mask = is_historical & (random_no_show < no_show_probability)
    cancel_mask = is_historical & ~no_show_mask & (random_cancel < cancellation_probability)
    completed_mask = is_historical & ~no_show_mask & ~cancel_mask
    status[no_show_mask] = "No-Show"
    status[cancel_mask] = "Cancelled"
    status[completed_mask] = "Completed"
    rescheduled_flag = ((rng.random(n) < (0.08 + 0.25 * cancel_mask.astype(float))) & is_historical).astype(int)

    return pd.DataFrame(
        {
            "appointment_id": _ids("A", n),
            "patient_id": patient_rows["patient_id"].to_numpy(),
            "department_id": dept_rows["department_id"].to_numpy(),
            "provider_id": provider_ids,
            "facility_id": dept_rows["facility_id"].to_numpy(),
            "booked_at": pd.to_datetime(booked_at).dt.strftime("%Y-%m-%d %H:%M:%S"),
            "scheduled_at": pd.to_datetime(scheduled_at).dt.strftime("%Y-%m-%d %H:%M:%S"),
            "appointment_date": sampled_dates.strftime("%Y-%m-%d"),
            "appointment_type": appointment_types,
            "booking_channel": booking_channel,
            "attendance_mode": attendance_mode,
            "service_priority": service_priority,
            "planned_duration_minutes": planned_duration,
            "reminder_sent": reminder_sent,
            "reminder_channel": reminder_channel,
            "status": status,
            "rescheduled_flag": rescheduled_flag,
            "synthetic_record": 1,
        }
    ).sort_values(["scheduled_at", "appointment_id"]).reset_index(drop=True)


def _build_staffing(
    config: GenerationConfig,
    appointments: pd.DataFrame,
    departments: pd.DataFrame,
    providers: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    dates = pd.date_range(config.start_date, config.as_of_date, freq="D")
    grid = pd.MultiIndex.from_product([departments["department_id"], dates.strftime("%Y-%m-%d")], names=["department_id", "staffing_date"]).to_frame(index=False)
    appt_counts = appointments[appointments["appointment_date"] <= config.as_of_date].groupby(["department_id", "appointment_date"]).size().rename("appointments").reset_index()
    appt_counts = appt_counts.rename(columns={"appointment_date": "staffing_date"})
    grid = grid.merge(appt_counts, on=["department_id", "staffing_date"], how="left")
    grid["appointments"] = grid["appointments"].fillna(0).astype(int)
    dept = departments.set_index("department_id")
    provider_capacity = providers.groupby("department_id")["weekly_capacity_hours"].sum() / 5.0
    grid["slots"] = grid["department_id"].map(dept["appointment_slots_daily"])
    grid["standard_service"] = grid["department_id"].map(dept["standard_service_minutes"])
    grid["base_hours"] = grid["department_id"].map(provider_capacity).fillna(8.0)
    weekday = pd.to_datetime(grid["staffing_date"]).dt.weekday
    open_factor = np.where(weekday < 5, 1.0, 0.20)
    required = np.maximum(0.0, grid["appointments"].to_numpy() * grid["standard_service"].to_numpy() / 60.0 * 1.22 + 1.5 * open_factor)
    planned = np.maximum(0.0, grid["base_hours"].to_numpy() * open_factor * rng.normal(0.96, 0.07, size=len(grid)))
    absence = np.maximum(0.0, rng.gamma(1.1, 0.45, size=len(grid)) * (rng.random(len(grid)) < 0.18))
    overtime = np.maximum(0.0, (required - planned + absence) * rng.uniform(0.10, 0.45, size=len(grid)))
    agency = np.maximum(0.0, (required - planned + absence - overtime) * rng.uniform(0.0, 0.25, size=len(grid)))
    actual = np.maximum(0.0, planned - absence + overtime + agency)
    staffing_gap = np.where(required > 0, np.clip((required - actual) / required, 0.0, 1.0), 0.0)
    result = pd.DataFrame(
        {
            "staffing_id": _ids("ST", len(grid), 9),
            "department_id": grid["department_id"],
            "staffing_date": grid["staffing_date"],
            "planned_hours": np.round(planned, 2),
            "actual_hours": np.round(actual, 2),
            "required_hours": np.round(required, 2),
            "overtime_hours": np.round(overtime, 2),
            "absence_hours": np.round(absence, 2),
            "agency_hours": np.round(agency, 2),
            "staffing_gap_rate": np.round(staffing_gap, 4),
            "synthetic_record": 1,
        }
    )
    return result


def _build_operational_events(
    appointments: pd.DataFrame,
    departments: pd.DataFrame,
    staffing: pd.DataFrame,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    completed = appointments[appointments["status"] == "Completed"].copy().reset_index(drop=True)
    cancelled = appointments[appointments["status"] == "Cancelled"].copy().reset_index(drop=True)
    no_show = appointments[appointments["status"] == "No-Show"].copy().reset_index(drop=True)
    dept = departments.set_index("department_id")
    staff_key = staffing.set_index(["department_id", "staffing_date"])

    completed["capacity_slots"] = completed["department_id"].map(dept["appointment_slots_daily"]).astype(float)
    completed_counts = completed.groupby(["department_id", "appointment_date"])["appointment_id"].transform("count")
    completed["utilization"] = completed_counts / completed["capacity_slots"]
    completed["staffing_gap"] = [float(staff_key.loc[(d, dt), "staffing_gap_rate"]) for d, dt in zip(completed["department_id"], completed["appointment_date"])]
    scheduled_dt = pd.to_datetime(completed["scheduled_at"])
    peak_hour = scheduled_dt.dt.hour.between(10, 14).astype(float).to_numpy()
    priority = (completed["service_priority"].to_numpy() == "Time-sensitive").astype(float)
    pressure = np.maximum(0.0, completed["utilization"].to_numpy() - 0.75) + np.maximum(0.0, completed["staffing_gap"].to_numpy())

    arrival_offset = np.clip(rng.normal(-4, 11, size=len(completed)) + 3 * (completed["attendance_mode"].to_numpy() == "Virtual"), -30, 60)
    registration_wait = np.maximum(0.0, rng.gamma(1.7, 2.8, size=len(completed)) * (1 + 0.55 * pressure))
    assessment_wait = np.maximum(0.0, rng.gamma(1.6, 4.2, size=len(completed)) * (1 + 0.75 * pressure + 0.12 * peak_hour))
    consultation_wait = np.maximum(0.0, rng.gamma(2.0, 6.2, size=len(completed)) * (1 + 1.15 * pressure + 0.20 * peak_hour - 0.10 * priority))
    diagnostic_wait = np.maximum(0.0, rng.gamma(1.5, 4.5, size=len(completed)) * (1 + 0.90 * pressure))
    diagnostic_needed = np.isin(completed["appointment_type"].to_numpy(), ["Diagnostic Service", "Procedure / Service", "Assessment"])
    diagnostic_wait = diagnostic_wait * np.where(diagnostic_needed, 1.0, 0.35)
    total_wait = registration_wait + assessment_wait + consultation_wait + diagnostic_wait
    targets = completed["department_id"].map(dept["target_wait_minutes"]).to_numpy(dtype=float)
    wait_frame = pd.DataFrame(
        {
            "wait_time_id": _ids("W", len(completed), 9),
            "appointment_id": completed["appointment_id"],
            "arrival_offset_minutes": np.round(arrival_offset, 2),
            "registration_wait_minutes": np.round(registration_wait, 2),
            "assessment_wait_minutes": np.round(assessment_wait, 2),
            "consultation_wait_minutes": np.round(consultation_wait, 2),
            "diagnostic_service_wait_minutes": np.round(diagnostic_wait, 2),
            "total_wait_minutes": np.round(total_wait, 2),
            "target_wait_minutes": np.round(targets, 2),
            "wait_target_exceeded": (total_wait > targets).astype(int),
            "synthetic_record": 1,
        }
    )

    flow_rows: list[dict] = []
    service_rows: list[dict] = []
    flow_counter = 1
    service_counter = 1
    for index, appointment in enumerate(completed.itertuples(index=False)):
        base = pd.Timestamp(appointment.scheduled_at) + pd.Timedelta(minutes=float(arrival_offset[index]))
        service_base = float(appointment.planned_duration_minutes)
        stage_service = [0.0, 5.0, 0.0, 8.0, service_base * 0.52, service_base * 0.24, service_base * 0.18, 4.0]
        stage_queue = [0.0, registration_wait[index], assessment_wait[index], 0.0, consultation_wait[index], diagnostic_wait[index], 0.0, 0.0]
        current = base
        for stage_order, stage_name in enumerate(FLOW_STAGES, start=1):
            queue_minutes = float(stage_queue[stage_order - 1])
            current = current + pd.Timedelta(minutes=queue_minutes)
            duration = max(0.0, float(stage_service[stage_order - 1]) * rng.normal(1.0, 0.12))
            stage_start = current
            stage_end = stage_start + pd.Timedelta(minutes=duration)
            flow_rows.append(
                {
                    "flow_event_id": f"FL{flow_counter:010d}",
                    "appointment_id": appointment.appointment_id,
                    "stage_order": stage_order,
                    "stage_name": stage_name,
                    "stage_start": stage_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "stage_end": stage_end.strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_minutes": round(duration, 2),
                    "queue_minutes": round(queue_minutes, 2),
                    "completed_flag": 1,
                    "synthetic_record": 1,
                }
            )
            if stage_name in ["Registration", "Consultation", "Diagnostic/Service", "Discharge"]:
                event_type = {"Registration": "Check-in completed", "Consultation": "Service started", "Diagnostic/Service": "Resource utilized", "Discharge": "Visit completed"}[stage_name]
                exception_probability = min(0.42, 0.025 + 0.15 * max(0, pressure[index]) + 0.05 * (queue_minutes > 20))
                service_rows.append(
                    {
                        "service_event_id": f"SE{service_counter:010d}",
                        "appointment_id": appointment.appointment_id,
                        "event_timestamp": stage_start.strftime("%Y-%m-%d %H:%M:%S"),
                        "event_type": event_type,
                        "operational_category": stage_name,
                        "resource_type": "Virtual platform" if appointment.attendance_mode == "Virtual" else rng.choice(["Room", "Shared equipment", "Service station", "Provider time"]),
                        "event_duration_minutes": round(duration, 2),
                        "exception_flag": int(rng.random() < exception_probability),
                        "synthetic_record": 1,
                    }
                )
                service_counter += 1
            current = stage_end
            flow_counter += 1
    flow = pd.DataFrame(flow_rows)
    service_events = pd.DataFrame(service_rows)

    survey_mask = rng.random(len(completed)) < 0.66
    surveyed = completed.loc[survey_mask].reset_index(drop=True)
    surveyed_wait = total_wait[survey_mask]
    surveyed_target = targets[survey_mask]
    wait_ratio = surveyed_wait / np.maximum(surveyed_target, 1.0)
    overall = np.clip(4.55 - 1.15 * np.maximum(0.0, wait_ratio - 0.65) + rng.normal(0, 0.45, size=len(surveyed)), 1, 5)
    service_score = np.clip(overall + rng.normal(0.15, 0.35, size=len(surveyed)), 1, 5)
    communication = np.clip(overall + rng.normal(0.08, 0.38, size=len(surveyed)), 1, 5)
    wait_score = np.clip(5.1 - 1.6 * wait_ratio + rng.normal(0, 0.40, size=len(surveyed)), 1, 5)
    feedback = np.where(overall >= 4.3, "Positive service experience", np.where(wait_score < 3, "Waiting experience", np.where(communication < 3.2, "Communication", "General service quality")))
    satisfaction = pd.DataFrame(
        {
            "satisfaction_id": _ids("SAT", len(surveyed), 8),
            "appointment_id": surveyed["appointment_id"],
            "survey_date": (pd.to_datetime(surveyed["appointment_date"]) + pd.to_timedelta(rng.integers(0, 6, size=len(surveyed)), unit="D")).dt.strftime("%Y-%m-%d"),
            "overall_score": np.round(overall, 2),
            "service_score": np.round(service_score, 2),
            "communication_score": np.round(communication, 2),
            "wait_experience_score": np.round(wait_score, 2),
            "would_recommend": (overall >= 3.8).astype(int),
            "feedback_category": feedback,
            "synthetic_record": 1,
        }
    )

    cancellation_time = pd.to_datetime(cancelled["scheduled_at"]) - pd.to_timedelta(np.clip(rng.gamma(1.8, 22, size=len(cancelled)), 0.5, 240), unit="h")
    hours_before = (pd.to_datetime(cancelled["scheduled_at"]) - cancellation_time).dt.total_seconds() / 3600.0
    cancellation = pd.DataFrame(
        {
            "cancellation_id": _ids("CXL", len(cancelled), 8),
            "appointment_id": cancelled["appointment_id"],
            "cancelled_at": cancellation_time.dt.strftime("%Y-%m-%d %H:%M:%S"),
            "hours_before_appointment": np.round(hours_before, 2),
            "cancelled_by": rng.choice(["Patient", "Facility", "Provider", "Automated rule"], size=len(cancelled), p=[0.72, 0.13, 0.12, 0.03]),
            "cancellation_reason": rng.choice(["Schedule conflict", "Transportation", "Changed availability", "Service rescheduled", "Unknown"], size=len(cancelled), p=[0.34, 0.12, 0.23, 0.17, 0.14]),
            "rebooked_within_30d": (rng.random(len(cancelled)) < 0.61).astype(int),
            "synthetic_record": 1,
        }
    )

    no_show_frame = pd.DataFrame(
        {
            "no_show_id": _ids("NS", len(no_show), 8),
            "appointment_id": no_show["appointment_id"],
            "recorded_at": (pd.to_datetime(no_show["scheduled_at"]) + pd.to_timedelta(30, unit="m")).dt.strftime("%Y-%m-%d %H:%M:%S"),
            "confirmation_status": rng.choice(["Confirmed", "Unconfirmed", "Unable to reach"], size=len(no_show), p=[0.31, 0.45, 0.24]),
            "outreach_attempted": (rng.random(len(no_show)) < 0.77).astype(int),
            "operational_reason_category": rng.choice(["Unknown", "Transportation", "Schedule conflict", "Reminder not acknowledged", "Access issue"], size=len(no_show), p=[0.46, 0.13, 0.20, 0.14, 0.07]),
            "synthetic_record": 1,
        }
    )
    return wait_frame, flow, satisfaction, cancellation, no_show_frame, service_events


def _inject_and_clean(
    appointments: pd.DataFrame,
    wait_times: pd.DataFrame,
    staffing: pd.DataFrame,
    satisfaction: pd.DataFrame,
    providers: pd.DataFrame,
    config: GenerationConfig,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[dict], pd.DataFrame]:
    raw_appt = appointments.copy()
    raw_wait = wait_times.copy()
    raw_staff = staffing.copy()
    raw_sat = satisfaction.copy()
    issue_rows: list[dict] = []

    anomaly_n = max(1, int(len(raw_appt) * config.anomaly_rate))
    duplicate_sample = raw_appt.sample(n=anomaly_n, random_state=config.seed)
    raw_appt = pd.concat([raw_appt, duplicate_sample], ignore_index=True)
    issue_rows.append({"entity": "APPOINTMENT", "issue": "duplicate appointment_id", "count": anomaly_n})

    channel_indexes = rng.choice(len(raw_appt), size=anomaly_n, replace=False)
    raw_appt.loc[channel_indexes, "booking_channel"] = None
    issue_rows.append({"entity": "APPOINTMENT", "issue": "missing booking channel", "count": anomaly_n})

    provider_indexes = rng.choice(len(raw_appt), size=anomaly_n, replace=False)
    raw_appt.loc[provider_indexes, "provider_id"] = "INVALID_PROVIDER"
    issue_rows.append({"entity": "APPOINTMENT", "issue": "invalid provider key", "count": anomaly_n})

    date_indexes = rng.choice(len(raw_appt), size=anomaly_n, replace=False)
    raw_appt.loc[date_indexes, "booked_at"] = raw_appt.loc[date_indexes, "scheduled_at"]
    issue_rows.append({"entity": "APPOINTMENT", "issue": "booked_at not before scheduled_at", "count": anomaly_n})

    wait_anomaly_n = max(1, int(len(raw_wait) * config.anomaly_rate))
    wait_indexes = rng.choice(len(raw_wait), size=wait_anomaly_n, replace=False)
    raw_wait.loc[wait_indexes, "consultation_wait_minutes"] = -5.0
    issue_rows.append({"entity": "WAIT_TIME", "issue": "negative wait duration", "count": wait_anomaly_n})

    sat_anomaly_n = max(1, int(len(raw_sat) * config.anomaly_rate))
    sat_indexes = rng.choice(len(raw_sat), size=sat_anomaly_n, replace=False)
    raw_sat.loc[sat_indexes, "overall_score"] = 6.0
    issue_rows.append({"entity": "SATISFACTION", "issue": "score outside 1-5", "count": sat_anomaly_n})

    staff_anomaly_n = max(1, int(len(raw_staff) * config.anomaly_rate))
    staff_indexes = rng.choice(len(raw_staff), size=staff_anomaly_n, replace=False)
    raw_staff.loc[staff_indexes, "actual_hours"] = -2.0
    issue_rows.append({"entity": "STAFFING", "issue": "negative actual hours", "count": staff_anomaly_n})

    provider_by_dept = providers.groupby("department_id")["provider_id"].first().to_dict()
    clean_appt = raw_appt.drop_duplicates("appointment_id", keep="first").copy()
    clean_appt["booking_channel"] = clean_appt["booking_channel"].fillna("Unknown")
    invalid_provider = ~clean_appt["provider_id"].isin(providers["provider_id"])
    clean_appt.loc[invalid_provider, "provider_id"] = clean_appt.loc[invalid_provider, "department_id"].map(provider_by_dept)
    booked = pd.to_datetime(clean_appt["booked_at"])
    scheduled = pd.to_datetime(clean_appt["scheduled_at"])
    invalid_dates = booked >= scheduled
    clean_appt.loc[invalid_dates, "booked_at"] = (scheduled.loc[invalid_dates] - pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S")

    clean_wait = raw_wait.copy()
    wait_columns = ["registration_wait_minutes", "assessment_wait_minutes", "consultation_wait_minutes", "diagnostic_service_wait_minutes"]
    for column in wait_columns:
        clean_wait[column] = clean_wait[column].clip(lower=0)
    clean_wait["total_wait_minutes"] = clean_wait[wait_columns].sum(axis=1).round(2)
    clean_wait["wait_target_exceeded"] = (clean_wait["total_wait_minutes"] > clean_wait["target_wait_minutes"]).astype(int)

    clean_staff = raw_staff.copy()
    for column in ["planned_hours", "actual_hours", "required_hours", "overtime_hours", "absence_hours", "agency_hours"]:
        clean_staff[column] = clean_staff[column].clip(lower=0)
    clean_staff["staffing_gap_rate"] = np.where(clean_staff["required_hours"] > 0, np.clip((clean_staff["required_hours"] - clean_staff["actual_hours"]) / clean_staff["required_hours"], 0.0, 1.0), 0.0).round(4)

    clean_sat = raw_sat.copy()
    for column in ["overall_score", "service_score", "communication_score", "wait_experience_score"]:
        clean_sat[column] = clean_sat[column].clip(1, 5)

    anomaly_sample = pd.concat(
        [
            raw_appt.loc[channel_indexes[: min(10, len(channel_indexes))], ["appointment_id", "provider_id", "booked_at", "scheduled_at", "booking_channel"]].assign(source_entity="APPOINTMENT"),
            raw_wait.loc[wait_indexes[: min(10, len(wait_indexes))], ["appointment_id", "consultation_wait_minutes", "total_wait_minutes"]].assign(source_entity="WAIT_TIME"),
        ],
        ignore_index=True,
        sort=False,
    )
    return clean_appt, clean_wait, clean_staff, clean_sat, issue_rows, anomaly_sample


def _frame_hash(frame: pd.DataFrame) -> str:
    payload = pd.util.hash_pandas_object(frame, index=True).values.tobytes()
    return hashlib.sha256(payload).hexdigest()[:16]


def generate_synthetic_data(db_path: str | Path, config: GenerationConfig, manifest_path: str | Path) -> dict:
    rng = np.random.default_rng(config.seed)
    facilities = _build_facilities(config, rng)
    departments = _build_departments(config, facilities, rng)
    providers = _build_providers(departments, rng)
    patients, latent = _build_patients(config, rng)
    appointments = _build_appointments(config, patients, latent, facilities, departments, providers, rng)
    staffing = _build_staffing(config, appointments, departments, providers, rng)
    wait_times, flow, satisfaction, cancellation, no_show, service_events = _build_operational_events(appointments, departments, staffing, rng)
    appointments, wait_times, staffing, satisfaction, raw_issues, anomaly_sample = _inject_and_clean(
        appointments, wait_times, staffing, satisfaction, providers, config, rng
    )
    date_dimension = _date_dimension(pd.Timestamp(config.start_date), pd.Timestamp(config.end_date) + pd.Timedelta(days=config.forecast_horizon_days))

    frames = {
        "FACILITY": facilities,
        "DEPARTMENT": departments,
        "PROVIDER": providers,
        "PATIENT": patients,
        "APPOINTMENT": appointments,
        "WAIT_TIME": wait_times,
        "PATIENT_FLOW": flow,
        "SATISFACTION": satisfaction,
        "CANCELLATION": cancellation,
        "NO_SHOW": no_show,
        "STAFFING": staffing,
        "SERVICE_EVENT": service_events,
        "DATE_DIMENSION": date_dimension,
    }
    for table, frame in frames.items():
        replace_table(db_path, frame, table, chunksize=25_000)

    RAW_SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    anomaly_sample.to_csv(RAW_SAMPLE_DIR / "raw_anomaly_sample.csv", index=False)
    pd.DataFrame(raw_issues).to_csv(RAW_SAMPLE_DIR / "injected_issue_summary.csv", index=False)

    manifest = {
        "platform": "CareIQ — Healthcare Operations & Patient Experience Intelligence Platform",
        "tagline": "From Healthcare Data to Better Operational Decisions.",
        "data_notice": "All records are fictional and synthetic. They are not official Canadian healthcare statistics.",
        "safety_notice": "Operational analytics prototype only. Not a medical diagnostic or treatment system.",
        "dataset_name": config.dataset_name,
        "dataset_version": f"{config.dataset_name}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generation_config": asdict(config),
        "row_counts": {table: int(len(frame)) for table, frame in frames.items()},
        "table_hashes": {table: _frame_hash(frame) for table, frame in frames.items()},
        "injected_raw_issues": raw_issues,
    }
    Path(manifest_path).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
