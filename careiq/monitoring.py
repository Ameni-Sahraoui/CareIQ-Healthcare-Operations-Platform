from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from careiq.database import read_frame, replace_table


def _psi(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    reference = pd.to_numeric(reference, errors="coerce").dropna()
    current = pd.to_numeric(current, errors="coerce").dropna()
    if reference.empty or current.empty:
        return float("nan")
    quantiles = np.unique(reference.quantile(np.linspace(0, 1, bins + 1)).to_numpy())
    if len(quantiles) < 3:
        return 0.0
    quantiles[0] = -np.inf
    quantiles[-1] = np.inf
    ref_counts = pd.cut(reference, quantiles, include_lowest=True).value_counts(sort=False).to_numpy(dtype=float)
    cur_counts = pd.cut(current, quantiles, include_lowest=True).value_counts(sort=False).to_numpy(dtype=float)
    ref_pct = np.clip(ref_counts / max(ref_counts.sum(), 1.0), 1e-6, None)
    cur_pct = np.clip(cur_counts / max(cur_counts.sum(), 1.0), 1e-6, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def compute_monitoring(db_path: str | Path, bundle_path: str | Path) -> pd.DataFrame:
    bundle = joblib.load(bundle_path)
    model_version = bundle["model_version"]
    measured_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    appointment = read_frame(db_path, "SELECT * FROM APPOINTMENT_FEATURE WHERE no_show_label IS NOT NULL ORDER BY scheduled_at")
    if not appointment.empty:
        appointment["scheduled_at_dt"] = pd.to_datetime(appointment["scheduled_at"])
        split_date = appointment["scheduled_at_dt"].quantile(0.75)
        reference = appointment[appointment["scheduled_at_dt"] < split_date]
        current = appointment[appointment["scheduled_at_dt"] >= split_date]
        for feature in ["lead_days", "prior_no_shows", "prior_cancellations", "utilization_ratio", "staffing_gap_rate", "planned_duration_minutes"]:
            drift = _psi(reference[feature], current[feature])
            status = "UNAVAILABLE" if not np.isfinite(drift) else "OK" if drift < 0.10 else "WATCH" if drift < 0.25 else "ALERT"
            rows.append(
                {
                    "monitoring_id": f"MON_{len(rows)+1:05d}",
                    "task_name": "appointment_models",
                    "metric_name": f"PSI: {feature}",
                    "reference_value": float(reference[feature].mean()),
                    "current_value": float(current[feature].mean()),
                    "drift_value": drift if np.isfinite(drift) else None,
                    "status": status,
                    "measured_at": measured_at,
                    "model_version": model_version,
                }
            )
    predictions = read_frame(db_path, "SELECT task_name, probability FROM PREDICTION")
    for task, group in predictions.groupby("task_name"):
        mean_probability = float(group["probability"].mean())
        rows.append(
            {
                "monitoring_id": f"MON_{len(rows)+1:05d}",
                "task_name": task,
                "metric_name": "Current mean predicted risk",
                "reference_value": None,
                "current_value": mean_probability,
                "drift_value": None,
                "status": "INFORMATIONAL",
                "measured_at": measured_at,
                "model_version": model_version,
            }
        )
    forecast = read_frame(db_path, "SELECT forecast_count, lower_bound, upper_bound FROM DEMAND_FORECAST")
    if not forecast.empty:
        interval_width = float((forecast["upper_bound"] - forecast["lower_bound"]).mean())
        rows.append(
            {
                "monitoring_id": f"MON_{len(rows)+1:05d}",
                "task_name": "demand_forecast",
                "metric_name": "Mean forecast interval width",
                "reference_value": None,
                "current_value": interval_width,
                "drift_value": None,
                "status": "INFORMATIONAL",
                "measured_at": measured_at,
                "model_version": model_version,
            }
        )
    frame = pd.DataFrame(rows)
    replace_table(db_path, frame, "MODEL_MONITORING")
    return frame
