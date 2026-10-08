from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from careiq.database import connect, read_frame, replace_table


def _clean_feature_name(name: str) -> str:
    cleaned = name.replace("num__", "").replace("cat__", "")
    return cleaned.replace("_", " ")


def _extract_shap(model, transformed, selected_model: str) -> np.ndarray:
    try:
        import shap

        if selected_model in ["XGBoost", "Random Forest"]:
            matrix = transformed.toarray() if selected_model == "Random Forest" and hasattr(transformed, "toarray") else transformed
            explainer = shap.TreeExplainer(model)
            values = explainer.shap_values(matrix, approximate=True, check_additivity=False)
        else:
            dense = transformed.toarray() if hasattr(transformed, "toarray") else np.asarray(transformed)
            values = dense * np.asarray(model.coef_[0])
        values = np.asarray(values)
        if values.ndim == 3:
            values = values[:, :, -1]
        if values.ndim == 1:
            values = values.reshape(1, -1)
        return values
    except Exception:
        dense = transformed.toarray() if hasattr(transformed, "toarray") else np.asarray(transformed)
        if hasattr(model, "feature_importances_"):
            return dense * np.asarray(model.feature_importances_)
        if hasattr(model, "coef_"):
            return dense * np.asarray(model.coef_[0])
        return np.zeros_like(dense, dtype=float)


def _appointment_source(db_path: str | Path, task: str) -> tuple[pd.DataFrame, str]:
    frame = read_frame(db_path, "SELECT * FROM APPOINTMENT_FEATURE ORDER BY scheduled_at, appointment_id")
    target = {"no_show": "no_show_label", "cancellation": "cancellation_label", "wait_time_risk": "wait_risk_label"}[task]
    frame = frame[frame[target].notna()].copy()
    if task == "wait_time_risk":
        frame = frame[frame["total_wait_minutes"].notna()].copy()
    return frame, target


def _capacity_source(db_path: str | Path) -> pd.DataFrame:
    frame = read_frame(db_path, "SELECT * FROM DEPARTMENT_DAILY ORDER BY activity_date, department_id")
    frame["activity_date_dt"] = pd.to_datetime(frame["activity_date"])
    frame["day_of_week"] = frame["activity_date_dt"].dt.weekday
    frame["month"] = frame["activity_date_dt"].dt.month
    frame = frame.sort_values(["department_id", "activity_date_dt"])
    grouped = frame.groupby("department_id")["scheduled_appointments"]
    frame["lag_1"] = grouped.shift(1)
    frame["lag_7"] = grouped.shift(7)
    frame["rolling_7"] = grouped.transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
    frame["rolling_28"] = grouped.transform(lambda s: s.shift(1).rolling(28, min_periods=1).mean())
    frame[["lag_1", "lag_7", "rolling_7", "rolling_28"]] = frame[["lag_1", "lag_7", "rolling_7", "rolling_28"]].fillna(0.0)
    return frame


def generate_explanations(db_path: str | Path, bundle_path: str | Path, sample_size: int = 700) -> dict:
    bundle = joblib.load(bundle_path)
    model_version = bundle["model_version"]
    global_rows: list[dict] = []
    segment_rows: list[dict] = []
    task_summaries: dict[str, dict] = {}

    for task, task_bundle in bundle["tasks"].items():
        print(f"  Explaining task: {task}", flush=True)
        if task == "capacity_pressure":
            source = _capacity_source(db_path)
            segment_column = "department_group"
        else:
            source, _ = _appointment_source(db_path, task)
            segment_column = "department_group"
        columns = task_bundle["categorical_features"] + task_bundle["numeric_features"]
        if source.empty:
            continue
        sample = source.tail(min(sample_size, len(source))).copy()
        pipeline = task_bundle["pipeline"]
        transformed = pipeline.named_steps["preprocessor"].transform(sample[columns])
        shap_values = _extract_shap(pipeline.named_steps["model"], transformed, task_bundle["selected_model"])
        feature_names = np.array(task_bundle["feature_names"], dtype=object)
        global_importance = np.mean(np.abs(shap_values), axis=0)
        order = np.argsort(global_importance)[::-1][:25]
        for rank, index in enumerate(order, start=1):
            global_rows.append(
                {
                    "explanation_id": f"GX_{task}_{rank:03d}",
                    "task_name": task,
                    "model_version": model_version,
                    "feature_name": _clean_feature_name(str(feature_names[index])),
                    "importance_value": float(global_importance[index]),
                    "importance_rank": rank,
                    "explanation_type": "SHAP mean absolute contribution" if task_bundle["selected_model"] != "Logistic Regression" else "Linear contribution proxy",
                }
            )
        sample = sample.reset_index(drop=True)
        for segment, indexes in sample.groupby(segment_column).groups.items():
            idx = np.array(list(indexes), dtype=int)
            if len(idx) < 15:
                continue
            segment_importance = np.mean(np.abs(shap_values[idx]), axis=0)
            segment_signed = np.mean(shap_values[idx], axis=0)
            segment_order = np.argsort(segment_importance)[::-1][:8]
            for feature_index in segment_order:
                direction = "raises predicted operational risk" if segment_signed[feature_index] > 0 else "reduces predicted operational risk"
                segment_rows.append(
                    {
                        "explanation_id": f"SX_{task}_{len(segment_rows)+1:06d}",
                        "task_name": task,
                        "segment_name": str(segment),
                        "feature_name": _clean_feature_name(str(feature_names[feature_index])),
                        "mean_abs_shap": float(segment_importance[feature_index]),
                        "direction_text": direction,
                        "model_version": model_version,
                    }
                )
        task_summaries[task] = {
            "sample_rows": int(len(sample)),
            "feature_count": int(len(feature_names)),
            "selected_model": task_bundle["selected_model"],
            "top_global_features": [_clean_feature_name(str(feature_names[index])) for index in order[:5]],
        }

    replace_table(db_path, pd.DataFrame(global_rows), "GLOBAL_EXPLANATION")
    replace_table(db_path, pd.DataFrame(segment_rows), "SEGMENT_EXPLANATION")
    print("  Updating individual appointment factors", flush=True)
    _update_prediction_factors(db_path, bundle)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "tasks": task_summaries, "global_rows": len(global_rows), "segment_rows": len(segment_rows)}


def _update_prediction_factors(db_path: str | Path, bundle: dict) -> None:
    future = read_frame(db_path, "SELECT * FROM APPOINTMENT_FEATURE WHERE no_show_label IS NULL ORDER BY scheduled_at")
    if future.empty:
        return
    with connect(db_path) as connection:
        for task in ["no_show", "cancellation", "wait_time_risk"]:
            task_bundle = bundle["tasks"][task]
            columns = task_bundle["categorical_features"] + task_bundle["numeric_features"]
            pipeline = task_bundle["pipeline"]
            transformed = pipeline.named_steps["preprocessor"].transform(future[columns])
            values = _extract_shap(pipeline.named_steps["model"], transformed, task_bundle["selected_model"])
            names = np.array(task_bundle["feature_names"], dtype=object)
            top_indices = np.argsort(np.abs(values), axis=1)[:, ::-1][:, :3]
            updates = []
            for appointment_id, row_indices, row_values in zip(future["appointment_id"], top_indices, values):
                factors = []
                for index in row_indices:
                    direction = "higher risk" if row_values[index] > 0 else "lower risk"
                    factors.append(f"{_clean_feature_name(str(names[index]))} ({direction})")
                updates.append((factors[0], factors[1], factors[2], f"PR_{task}_{appointment_id}"))
            connection.executemany(
                "UPDATE PREDICTION SET top_factor_1 = ?, top_factor_2 = ?, top_factor_3 = ? WHERE prediction_id = ?",
                updates,
            )
        connection.commit()
