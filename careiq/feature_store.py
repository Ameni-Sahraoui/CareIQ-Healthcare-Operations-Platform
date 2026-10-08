from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd

from careiq.config import MANIFEST_PATH
from careiq.database import read_frame, replace_table


def _dataset_version(manifest_path: str | Path) -> str:
    path = Path(manifest_path)
    if not path.exists():
        return "careiq_unversioned"
    return json.loads(path.read_text(encoding="utf-8")).get("dataset_version", "careiq_unversioned")


def build_feature_store(db_path: str | Path, manifest_path: str | Path = MANIFEST_PATH) -> dict:
    version = _dataset_version(manifest_path)
    appointments = read_frame(db_path, "SELECT * FROM APPOINTMENT")
    patients = read_frame(db_path, "SELECT * FROM PATIENT")
    departments = read_frame(db_path, "SELECT * FROM DEPARTMENT")
    facilities = read_frame(db_path, "SELECT facility_id, province FROM FACILITY")
    staffing = read_frame(db_path, "SELECT * FROM STAFFING")
    waits = read_frame(db_path, "SELECT * FROM WAIT_TIME")
    satisfaction = read_frame(db_path, "SELECT appointment_id, overall_score FROM SATISFACTION")

    appointments["scheduled_at_dt"] = pd.to_datetime(appointments["scheduled_at"])
    appointments["booked_at_dt"] = pd.to_datetime(appointments["booked_at"])
    appointments = appointments.sort_values(["patient_id", "scheduled_at_dt", "appointment_id"]).reset_index(drop=True)
    appointments["no_show_label"] = np.where(appointments["status"] == "Scheduled", np.nan, (appointments["status"] == "No-Show").astype(int))
    appointments["cancellation_label"] = np.where(appointments["status"] == "Scheduled", np.nan, (appointments["status"] == "Cancelled").astype(int))
    appointments["prior_appointments"] = appointments.groupby("patient_id").cumcount()
    appointments["prior_no_shows"] = appointments.groupby("patient_id")["no_show_label"].transform(lambda s: s.fillna(0).cumsum().shift(1).fillna(0)).astype(int)
    appointments["prior_cancellations"] = appointments.groupby("patient_id")["cancellation_label"].transform(lambda s: s.fillna(0).cumsum().shift(1).fillna(0)).astype(int)
    prior_attended = appointments["prior_appointments"] - appointments["prior_no_shows"] - appointments["prior_cancellations"]
    appointments["prior_attendance_rate"] = np.where(appointments["prior_appointments"] > 0, prior_attended / appointments["prior_appointments"], 1.0)
    appointments["previous_scheduled_at"] = appointments.groupby("patient_id")["scheduled_at_dt"].shift(1)
    appointments["days_since_prior_appointment"] = (appointments["scheduled_at_dt"] - appointments["previous_scheduled_at"]).dt.total_seconds() / 86400.0
    appointments["lead_days"] = (appointments["scheduled_at_dt"] - appointments["booked_at_dt"]).dt.total_seconds() / 86400.0
    appointments["appointment_hour"] = appointments["scheduled_at_dt"].dt.hour
    appointments["day_of_week"] = appointments["scheduled_at_dt"].dt.weekday
    appointments["month"] = appointments["scheduled_at_dt"].dt.month

    daily_counts = appointments.groupby(["department_id", "appointment_date"]).size().rename("department_daily_bookings").reset_index()
    staffing_small = staffing[["department_id", "staffing_date", "staffing_gap_rate", "overtime_hours", "actual_hours"]].copy()
    staffing_small["overtime_rate"] = np.where(staffing_small["actual_hours"] > 0, staffing_small["overtime_hours"] / staffing_small["actual_hours"], 0.0)
    staffing_small = staffing_small.rename(columns={"staffing_date": "appointment_date"})
    dept_cols = departments[["department_id", "facility_id", "department_group", "appointment_slots_daily", "target_wait_minutes"]]
    patient_cols = patients[["patient_id", "age_band", "rurality", "accessibility_support_flag"]]
    facility_cols = facilities.rename(columns={"province": "facility_province"})

    features = appointments.merge(patient_cols, on="patient_id", how="left")
    features = features.merge(dept_cols, on=["department_id", "facility_id"], how="left")
    features = features.merge(facility_cols, on="facility_id", how="left")
    features = features.merge(daily_counts, on=["department_id", "appointment_date"], how="left")
    features = features.merge(staffing_small[["department_id", "appointment_date", "staffing_gap_rate", "overtime_rate"]], on=["department_id", "appointment_date"], how="left")
    future_gap_fill = staffing.groupby("department_id")["staffing_gap_rate"].median()
    future_ot_fill = staffing_small.groupby("department_id")["overtime_rate"].median()
    features["staffing_gap_rate"] = features["staffing_gap_rate"].fillna(features["department_id"].map(future_gap_fill)).fillna(0.0)
    features["overtime_rate"] = features["overtime_rate"].fillna(features["department_id"].map(future_ot_fill)).fillna(0.0)
    features["utilization_ratio"] = features["department_daily_bookings"] / features["appointment_slots_daily"].clip(lower=1)
    features = features.merge(waits[["appointment_id", "total_wait_minutes", "target_wait_minutes", "wait_target_exceeded"]], on="appointment_id", how="left", suffixes=("", "_wait"))
    features["wait_risk_label"] = features["wait_target_exceeded"]
    features["target_wait_minutes"] = features["target_wait_minutes_wait"].fillna(features["target_wait_minutes"])

    appointment_feature = pd.DataFrame(
        {
            "appointment_id": features["appointment_id"],
            "scheduled_at": features["scheduled_at"],
            "appointment_date": features["appointment_date"],
            "patient_id": features["patient_id"],
            "department_id": features["department_id"],
            "facility_id": features["facility_id"],
            "province": features["facility_province"],
            "department_group": features["department_group"],
            "appointment_type": features["appointment_type"],
            "booking_channel": features["booking_channel"],
            "attendance_mode": features["attendance_mode"],
            "service_priority": features["service_priority"],
            "lead_days": features["lead_days"].clip(lower=0),
            "appointment_hour": features["appointment_hour"],
            "day_of_week": features["day_of_week"],
            "month": features["month"],
            "reminder_sent": features["reminder_sent"],
            "rescheduled_flag": features["rescheduled_flag"],
            "prior_appointments": features["prior_appointments"],
            "prior_no_shows": features["prior_no_shows"],
            "prior_cancellations": features["prior_cancellations"],
            "prior_attendance_rate": features["prior_attendance_rate"].clip(0, 1),
            "days_since_prior_appointment": features["days_since_prior_appointment"],
            "department_daily_bookings": features["department_daily_bookings"].fillna(0).astype(int),
            "department_capacity_slots": features["appointment_slots_daily"].astype(int),
            "utilization_ratio": features["utilization_ratio"].clip(lower=0),
            "staffing_gap_rate": features["staffing_gap_rate"],
            "overtime_rate": features["overtime_rate"].clip(lower=0),
            "planned_duration_minutes": features["planned_duration_minutes"].astype(float),
            "accessibility_support_flag": features["accessibility_support_flag"].astype(int),
            "rurality": features["rurality"],
            "age_band": features["age_band"],
            "no_show_label": features["no_show_label"],
            "cancellation_label": features["cancellation_label"],
            "wait_risk_label": features["wait_risk_label"],
            "total_wait_minutes": features["total_wait_minutes"],
            "target_wait_minutes": features["target_wait_minutes"],
            "feature_version": "appointment_features_v1",
        }
    )
    replace_table(db_path, appointment_feature, "APPOINTMENT_FEATURE")

    as_of_date = staffing["staffing_date"].max()
    historical = appointments[appointments["appointment_date"] <= as_of_date].copy()
    department_dates = pd.MultiIndex.from_product(
        [departments["department_id"], pd.date_range(historical["appointment_date"].min(), as_of_date, freq="D").strftime("%Y-%m-%d")],
        names=["department_id", "activity_date"],
    ).to_frame(index=False)
    status_counts = historical.pivot_table(index=["department_id", "appointment_date"], columns="status", values="appointment_id", aggfunc="count", fill_value=0).reset_index()
    status_counts.columns.name = None
    status_counts = status_counts.rename(columns={"appointment_date": "activity_date"})
    for status in ["Completed", "No-Show", "Cancelled", "Scheduled"]:
        if status not in status_counts:
            status_counts[status] = 0
    daily = department_dates.merge(status_counts, on=["department_id", "activity_date"], how="left").fillna({"Completed": 0, "No-Show": 0, "Cancelled": 0, "Scheduled": 0})
    daily["scheduled_appointments"] = daily[["Completed", "No-Show", "Cancelled", "Scheduled"]].sum(axis=1).astype(int)
    daily = daily.merge(departments[["department_id", "facility_id", "department_group", "appointment_slots_daily", "target_wait_minutes"]], on="department_id", how="left")
    daily = daily.merge(facilities.rename(columns={"province": "province"}), on="facility_id", how="left")
    daily = daily.merge(staffing[["department_id", "staffing_date", "staffing_gap_rate", "overtime_hours"]].rename(columns={"staffing_date": "activity_date"}), on=["department_id", "activity_date"], how="left")

    wait_daily = waits.merge(appointments[["appointment_id", "department_id", "appointment_date"]], on="appointment_id", how="left")
    wait_agg = wait_daily.groupby(["department_id", "appointment_date"])["total_wait_minutes"].agg(
        average_wait_minutes="mean",
        median_wait_minutes="median",
        p90_wait_minutes=lambda s: s.quantile(0.90),
    ).reset_index().rename(columns={"appointment_date": "activity_date"})
    sat_daily = satisfaction.merge(appointments[["appointment_id", "department_id", "appointment_date"]], on="appointment_id", how="left").groupby(["department_id", "appointment_date"])["overall_score"].mean().rename("satisfaction_score").reset_index().rename(columns={"appointment_date": "activity_date"})
    daily = daily.merge(wait_agg, on=["department_id", "activity_date"], how="left")
    daily = daily.merge(sat_daily, on=["department_id", "activity_date"], how="left")
    daily["staffing_gap_rate"] = daily["staffing_gap_rate"].fillna(0.0)
    daily["overtime_hours"] = daily["overtime_hours"].fillna(0.0)
    daily["utilization_ratio"] = daily["scheduled_appointments"] / daily["appointment_slots_daily"].clip(lower=1)
    daily["capacity_pressure_label"] = (
        (daily["utilization_ratio"] >= 0.90)
        | (daily["staffing_gap_rate"] >= 0.15)
        | (daily["p90_wait_minutes"].fillna(0) > daily["target_wait_minutes"] * 1.35)
    ).astype(int)

    department_daily = pd.DataFrame(
        {
            "department_id": daily["department_id"],
            "activity_date": daily["activity_date"],
            "facility_id": daily["facility_id"],
            "province": daily["province"],
            "department_group": daily["department_group"],
            "scheduled_appointments": daily["scheduled_appointments"].astype(int),
            "completed_appointments": daily["Completed"].astype(int),
            "no_shows": daily["No-Show"].astype(int),
            "cancellations": daily["Cancelled"].astype(int),
            "capacity_slots": daily["appointment_slots_daily"].astype(int),
            "utilization_ratio": daily["utilization_ratio"],
            "average_wait_minutes": daily["average_wait_minutes"],
            "median_wait_minutes": daily["median_wait_minutes"],
            "p90_wait_minutes": daily["p90_wait_minutes"],
            "satisfaction_score": daily["satisfaction_score"],
            "staffing_gap_rate": daily["staffing_gap_rate"],
            "overtime_hours": daily["overtime_hours"],
            "capacity_pressure_label": daily["capacity_pressure_label"].astype(int),
            "dataset_version": version,
        }
    )
    replace_table(db_path, department_daily, "DEPARTMENT_DAILY", chunksize=25_000)
    return {
        "appointment_feature_rows": int(len(appointment_feature)),
        "department_daily_rows": int(len(department_daily)),
        "historical_appointments": int(appointment_feature["no_show_label"].notna().sum()),
        "future_scheduled_appointments": int(appointment_feature["no_show_label"].isna().sum()),
        "dataset_version": version,
    }
