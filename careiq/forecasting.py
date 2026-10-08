from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from careiq.config import MANIFEST_PATH
from careiq.database import read_frame, replace_table

FEATURES = [
    "department_code", "appointment_type_code", "day_of_week", "month", "trend_day",
    "dow_sin", "dow_cos", "month_sin", "month_cos", "lag_1", "lag_7", "lag_14", "rolling_7", "rolling_28",
]


def _manifest(manifest_path: str | Path = MANIFEST_PATH) -> dict:
    path = Path(manifest_path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _demand_grid(db_path: str | Path, as_of_date: str) -> tuple[pd.DataFrame, dict, dict]:
    appointments = read_frame(
        db_path,
        "SELECT department_id, appointment_type, appointment_date FROM APPOINTMENT WHERE date(appointment_date) <= date(?)",
        (as_of_date,),
    )
    appointments["appointment_date"] = pd.to_datetime(appointments["appointment_date"])
    counts = appointments.groupby(["department_id", "appointment_type", "appointment_date"]).size().rename("demand").reset_index()
    combos = counts[["department_id", "appointment_type"]].drop_duplicates().reset_index(drop=True)
    dates = pd.date_range(counts["appointment_date"].min(), pd.Timestamp(as_of_date), freq="D")
    combo_frame = combos.assign(key=1)
    date_frame = pd.DataFrame({"appointment_date": dates, "key": 1})
    grid = combo_frame.merge(date_frame, on="key").drop(columns="key")
    grid = grid.merge(counts, on=["department_id", "appointment_type", "appointment_date"], how="left")
    grid["demand"] = grid["demand"].fillna(0.0)
    department_codes = {value: index for index, value in enumerate(sorted(grid["department_id"].unique()))}
    type_codes = {value: index for index, value in enumerate(sorted(grid["appointment_type"].unique()))}
    grid["department_code"] = grid["department_id"].map(department_codes).astype(int)
    grid["appointment_type_code"] = grid["appointment_type"].map(type_codes).astype(int)
    grid = grid.sort_values(["department_id", "appointment_type", "appointment_date"]).reset_index(drop=True)
    grid["day_of_week"] = grid["appointment_date"].dt.weekday
    grid["month"] = grid["appointment_date"].dt.month
    grid["trend_day"] = (grid["appointment_date"] - grid["appointment_date"].min()).dt.days
    grid["dow_sin"] = np.sin(2 * np.pi * grid["day_of_week"] / 7)
    grid["dow_cos"] = np.cos(2 * np.pi * grid["day_of_week"] / 7)
    grid["month_sin"] = np.sin(2 * np.pi * grid["month"] / 12)
    grid["month_cos"] = np.cos(2 * np.pi * grid["month"] / 12)
    grouped = grid.groupby(["department_id", "appointment_type"])["demand"]
    grid["lag_1"] = grouped.shift(1)
    grid["lag_7"] = grouped.shift(7)
    grid["lag_14"] = grouped.shift(14)
    grid["rolling_7"] = grouped.transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
    grid["rolling_28"] = grouped.transform(lambda s: s.shift(1).rolling(28, min_periods=1).mean())
    grid[["lag_1", "lag_7", "lag_14", "rolling_7", "rolling_28"]] = grid[["lag_1", "lag_7", "lag_14", "rolling_7", "rolling_28"]].fillna(0.0)
    return grid, department_codes, type_codes


def _metrics(actual: np.ndarray, forecast: np.ndarray) -> dict[str, float]:
    forecast = np.clip(forecast, 0, None)
    mae = mean_absolute_error(actual, forecast)
    rmse = float(np.sqrt(mean_squared_error(actual, forecast)))
    denominator = max(float(np.abs(actual).sum()), 1.0)
    wape = float(np.abs(actual - forecast).sum() / denominator)
    return {"mae": float(mae), "rmse": rmse, "wape": wape}


def _candidate_models(seed: int) -> dict[str, object]:
    return {
        "HistGradientBoosting": HistGradientBoostingRegressor(max_iter=130, learning_rate=0.065, max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=0.15, random_state=seed),
        "RandomForestRegressor": RandomForestRegressor(n_estimators=55, max_depth=11, min_samples_leaf=5, max_features=0.75, n_jobs=-1, random_state=seed),
        "XGBoostRegressor": XGBRegressor(n_estimators=80, max_depth=4, learning_rate=0.07, subsample=0.86, colsample_bytree=0.82, reg_lambda=1.2, objective="reg:squarederror", n_jobs=4, random_state=seed),
    }


def train_forecast_model(
    db_path: str | Path,
    bundle_path: str | Path,
    metrics_path: str | Path,
    seed: int = 42,
    manifest_path: str | Path = MANIFEST_PATH,
) -> dict:
    manifest = _manifest(manifest_path)
    config = manifest.get("generation_config", {})
    as_of_date = config.get("as_of_date", read_frame(db_path, "SELECT MAX(activity_date) AS d FROM DEPARTMENT_DAILY").iloc[0, 0])
    horizon = int(config.get("forecast_horizon_days", 90))
    dataset_version = manifest.get("dataset_version", "careiq_unversioned")
    print("  Building daily demand grid", flush=True)
    grid, department_codes, type_codes = _demand_grid(db_path, as_of_date)
    print(f"  Demand grid rows: {len(grid):,}", flush=True)
    holdout_start = pd.Timestamp(as_of_date) - pd.Timedelta(days=59)
    train = grid[grid["appointment_date"] < holdout_start].copy()
    holdout = grid[grid["appointment_date"] >= holdout_start].copy()
    candidates: dict[str, dict] = {}
    fitted: dict[str, object] = {}

    baseline = holdout["lag_7"].to_numpy()
    baseline_metrics = _metrics(holdout["demand"].to_numpy(), baseline)
    baseline_residual = holdout["demand"].to_numpy() - baseline
    candidates["SeasonalNaive7"] = {"holdout": baseline_metrics}

    for name, model in _candidate_models(seed).items():
        print(f"  Fitting forecast candidate: {name}", flush=True)
        model.fit(train[FEATURES], train["demand"])
        prediction = np.clip(model.predict(holdout[FEATURES]), 0, None)
        candidates[name] = {"holdout": _metrics(holdout["demand"].to_numpy(), prediction)}
        fitted[name] = model

    selected_name = min(candidates, key=lambda name: candidates[name]["holdout"]["wape"])
    if selected_name == "SeasonalNaive7":
        selected_model = None
        selected_holdout_prediction = baseline
        residual = baseline_residual
    else:
        selected_model = fitted[selected_name]
        selected_holdout_prediction = np.clip(selected_model.predict(holdout[FEATURES]), 0, None)
        residual = holdout["demand"].to_numpy() - selected_holdout_prediction
    residual_width = float(np.quantile(np.abs(residual), 0.90))
    interval_lower = np.clip(selected_holdout_prediction - residual_width, 0, None)
    interval_upper = selected_holdout_prediction + residual_width
    interval_coverage = float(np.mean((holdout["demand"].to_numpy() >= interval_lower) & (holdout["demand"].to_numpy() <= interval_upper)))
    holdout_evaluation = holdout[["department_id", "appointment_type", "appointment_date", "demand"]].copy()
    holdout_evaluation["forecast"] = selected_holdout_prediction
    granularity_metrics = {"daily": _metrics(holdout_evaluation["demand"].to_numpy(), holdout_evaluation["forecast"].to_numpy())}
    for label, period in [("weekly", "W"), ("monthly", "M")]:
        grouped = holdout_evaluation.assign(period=holdout_evaluation["appointment_date"].dt.to_period(period).astype(str)).groupby(["department_id", "appointment_type", "period"], as_index=False)[["demand", "forecast"]].sum()
        granularity_metrics[label] = _metrics(grouped["demand"].to_numpy(), grouped["forecast"].to_numpy())

    print(f"  Selected forecast model: {selected_name}", flush=True)
    if selected_model is not None:
        print("  Refitting selected forecast model on full history", flush=True)
        selected_model.fit(grid[FEATURES], grid["demand"])

    history: dict[tuple[str, str], list[float]] = {}
    for (department_id, appointment_type), group in grid.groupby(["department_id", "appointment_type"], sort=False):
        history[(department_id, appointment_type)] = group.sort_values("appointment_date")["demand"].astype(float).tolist()

    last_date = pd.Timestamp(as_of_date)
    first_date = grid["appointment_date"].min()
    forecast_rows: list[dict] = []
    forecast_version = f"careiq_demand_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    combo_list = list(grid[["department_id", "appointment_type"]].drop_duplicates().itertuples(index=False))
    print(f"  Forecasting {len(combo_list)} department/type series for {horizon} days", flush=True)
    for horizon_day in range(1, horizon + 1):
        forecast_date = last_date + pd.Timedelta(days=horizon_day)
        feature_rows = []
        keys = []
        lag7_values = []
        for combo in combo_list:
            key = (combo.department_id, combo.appointment_type)
            series = history[key]
            lag_1 = series[-1] if len(series) >= 1 else 0.0
            lag_7 = series[-7] if len(series) >= 7 else lag_1
            lag_14 = series[-14] if len(series) >= 14 else lag_7
            rolling_7 = float(np.mean(series[-7:])) if series else 0.0
            rolling_28 = float(np.mean(series[-28:])) if series else 0.0
            day_of_week = forecast_date.weekday()
            month = forecast_date.month
            feature_rows.append(
                {
                    "department_code": department_codes[combo.department_id],
                    "appointment_type_code": type_codes[combo.appointment_type],
                    "day_of_week": day_of_week,
                    "month": month,
                    "trend_day": (forecast_date - first_date).days,
                    "dow_sin": np.sin(2 * np.pi * day_of_week / 7),
                    "dow_cos": np.cos(2 * np.pi * day_of_week / 7),
                    "month_sin": np.sin(2 * np.pi * month / 12),
                    "month_cos": np.cos(2 * np.pi * month / 12),
                    "lag_1": lag_1,
                    "lag_7": lag_7,
                    "lag_14": lag_14,
                    "rolling_7": rolling_7,
                    "rolling_28": rolling_28,
                }
            )
            keys.append(key)
            lag7_values.append(lag_7)
        day_features = pd.DataFrame(feature_rows)
        values = np.asarray(lag7_values, dtype=float) if selected_model is None else np.clip(selected_model.predict(day_features[FEATURES]), 0, None)
        for combo, key, value in zip(combo_list, keys, values):
            value = max(0.0, float(value))
            history[key].append(value)
            forecast_rows.append(
                {
                    "forecast_id": f"FC_{combo.department_id}_{type_codes[combo.appointment_type]:02d}_{forecast_date.strftime('%Y%m%d')}",
                    "department_id": combo.department_id,
                    "appointment_type": combo.appointment_type,
                    "forecast_date": forecast_date.strftime("%Y-%m-%d"),
                    "horizon_days": horizon_day,
                    "forecast_count": round(value, 4),
                    "lower_bound": round(max(0.0, value - residual_width), 4),
                    "upper_bound": round(value + residual_width, 4),
                    "model_name": selected_name,
                    "model_version": forecast_version,
                    "dataset_version": dataset_version,
                }
            )
    forecast_frame = pd.DataFrame(forecast_rows)
    replace_table(db_path, forecast_frame, "DEMAND_FORECAST", chunksize=25_000)

    document = {
        "forecast_model_version": forecast_version,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset_version,
        "as_of_date": as_of_date,
        "forecast_horizon_days": horizon,
        "holdout_start": holdout_start.strftime("%Y-%m-%d"),
        "holdout_rows": int(len(holdout)),
        "selected_model": selected_name,
        "candidate_metrics": candidates,
        "prediction_interval_method": "Symmetric 90th-percentile absolute temporal-holdout residual interval.",
        "interval_half_width": residual_width,
        "holdout_interval_coverage": interval_coverage,
        "selected_model_metrics_by_granularity": granularity_metrics,
        "forecast_rows": int(len(forecast_frame)),
    }
    Path(metrics_path).write_text(json.dumps(document, indent=2), encoding="utf-8")

    bundle = joblib.load(bundle_path)
    bundle["forecasting"] = {
        "model": selected_model,
        "model_name": selected_name,
        "model_version": forecast_version,
        "features": FEATURES,
        "department_codes": department_codes,
        "appointment_type_codes": type_codes,
        "interval_half_width": residual_width,
        "as_of_date": as_of_date,
    }
    joblib.dump(bundle, bundle_path, compress=3)
    _score_future_capacity(db_path, bundle, forecast_frame, dataset_version)
    return document


def _score_future_capacity(db_path: str | Path, bundle: dict, forecast: pd.DataFrame, dataset_version: str) -> None:
    if forecast.empty:
        return
    task_bundle = bundle["tasks"]["capacity_pressure"]
    departments = read_frame(db_path, "SELECT department_id, facility_id, department_group, appointment_slots_daily FROM DEPARTMENT")
    facilities = read_frame(db_path, "SELECT facility_id, province FROM FACILITY")
    staffing = read_frame(db_path, "SELECT department_id, staffing_date, staffing_gap_rate, overtime_hours FROM STAFFING")
    staffing["day_of_week"] = pd.to_datetime(staffing["staffing_date"]).dt.weekday
    staff_typical = staffing.groupby(["department_id", "day_of_week"])[["staffing_gap_rate", "overtime_hours"]].median().reset_index()
    total_forecast = forecast.groupby(["department_id", "forecast_date"])["forecast_count"].sum().rename("scheduled_appointments").reset_index()
    total_forecast["activity_date_dt"] = pd.to_datetime(total_forecast["forecast_date"])
    total_forecast["day_of_week"] = total_forecast["activity_date_dt"].dt.weekday
    total_forecast["month"] = total_forecast["activity_date_dt"].dt.month
    total_forecast = total_forecast.merge(departments, on="department_id", how="left").merge(facilities, on="facility_id", how="left").merge(staff_typical, on=["department_id", "day_of_week"], how="left")
    total_forecast["capacity_slots"] = total_forecast["appointment_slots_daily"]
    total_forecast["utilization_ratio"] = total_forecast["scheduled_appointments"] / total_forecast["capacity_slots"].clip(lower=1)
    total_forecast["staffing_gap_rate"] = total_forecast["staffing_gap_rate"].fillna(0.0)
    total_forecast["overtime_hours"] = total_forecast["overtime_hours"].fillna(0.0)
    total_forecast = total_forecast.sort_values(["department_id", "activity_date_dt"])
    historical = read_frame(db_path, "SELECT department_id, activity_date, scheduled_appointments FROM DEPARTMENT_DAILY")
    historical["activity_date_dt"] = pd.to_datetime(historical["activity_date"])
    series_map = {d: g.sort_values("activity_date_dt")["scheduled_appointments"].astype(float).tolist() for d, g in historical.groupby("department_id")}
    feature_rows = []
    for row in total_forecast.itertuples(index=False):
        series = series_map.setdefault(row.department_id, [])
        lag_1 = series[-1] if len(series) >= 1 else 0.0
        lag_7 = series[-7] if len(series) >= 7 else lag_1
        rolling_7 = float(np.mean(series[-7:])) if series else 0.0
        rolling_28 = float(np.mean(series[-28:])) if series else 0.0
        feature_rows.append(
            {
                "department_group": row.department_group,
                "province": row.province,
                "scheduled_appointments": row.scheduled_appointments,
                "capacity_slots": row.capacity_slots,
                "utilization_ratio": row.utilization_ratio,
                "staffing_gap_rate": row.staffing_gap_rate,
                "overtime_hours": row.overtime_hours,
                "day_of_week": row.day_of_week,
                "month": row.month,
                "lag_1": lag_1,
                "lag_7": lag_7,
                "rolling_7": rolling_7,
                "rolling_28": rolling_28,
            }
        )
        series.append(float(row.scheduled_appointments))
    feature_frame = pd.DataFrame(feature_rows)
    columns = task_bundle["categorical_features"] + task_bundle["numeric_features"]
    probabilities = task_bundle["pipeline"].predict_proba(feature_frame[columns])[:, 1]
    existing = read_frame(db_path, "SELECT * FROM PREDICTION")
    timestamp = datetime.now(timezone.utc).isoformat()
    rows = []
    for row, probability in zip(total_forecast.itertuples(index=False), probabilities):
        band = "Low" if probability < 0.30 else "Moderate" if probability < 0.50 else "High" if probability < 0.70 else "Critical"
        entity_id = f"{row.department_id}_{row.forecast_date}"
        suggestion = "Review staffing coverage, slot allocation and demand smoothing before the predicted high-pressure date." if band in ["High", "Critical"] else "Maintain routine capacity monitoring."
        rows.append(
            {
                "prediction_id": f"PR_future_capacity_{entity_id}",
                "entity_type": "DepartmentDayForecast",
                "entity_id": entity_id,
                "task_name": "capacity_pressure",
                "probability": float(probability),
                "risk_band": band,
                "prediction_timestamp": timestamp,
                "model_version": bundle["model_version"],
                "dataset_version": dataset_version,
                "top_factor_1": "Forecast demand versus available slots",
                "top_factor_2": "Typical staffing gap for weekday",
                "top_factor_3": "Recent department demand",
                "decision_support": suggestion,
                "limitations": "Synthetic operational simulation; not causal evidence and not a clinical recommendation.",
            }
        )
    combined = pd.concat([existing[~existing["prediction_id"].str.startswith("PR_future_capacity_", na=False)], pd.DataFrame(rows)], ignore_index=True)
    replace_table(db_path, combined, "PREDICTION", chunksize=20_000)
