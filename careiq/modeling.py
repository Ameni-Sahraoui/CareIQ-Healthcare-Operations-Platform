from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier

from careiq.config import MANIFEST_PATH
from careiq.database import read_frame, replace_table

warnings.filterwarnings("ignore", category=UserWarning)

APPOINTMENT_CATEGORICAL = [
    "department_group", "appointment_type", "booking_channel", "attendance_mode", "service_priority", "province"
]
APPOINTMENT_NUMERIC = [
    "lead_days", "appointment_hour", "day_of_week", "month", "reminder_sent", "rescheduled_flag",
    "prior_appointments", "prior_no_shows", "prior_cancellations", "prior_attendance_rate",
    "days_since_prior_appointment", "department_daily_bookings", "department_capacity_slots",
    "utilization_ratio", "staffing_gap_rate", "overtime_rate", "planned_duration_minutes",
]
CAPACITY_CATEGORICAL = ["department_group", "province"]
CAPACITY_NUMERIC = [
    "scheduled_appointments", "capacity_slots", "utilization_ratio", "staffing_gap_rate", "overtime_hours",
    "day_of_week", "month", "lag_1", "lag_7", "rolling_7", "rolling_28",
]


def _manifest_version(manifest_path: str | Path = MANIFEST_PATH) -> str:
    path = Path(manifest_path)
    if not path.exists():
        return "careiq_unversioned"
    return json.loads(path.read_text(encoding="utf-8")).get("dataset_version", "careiq_unversioned")


def _preprocessor(categorical: list[str], numeric: list[str]) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", min_frequency=20, sparse_output=True)),
        ]
    )
    return ColumnTransformer(
        [("num", numeric_pipe, numeric), ("cat", categorical_pipe, categorical)],
        remainder="drop",
        sparse_threshold=0.2,
    )


def _models(seed: int) -> dict[str, object]:
    return {
        "Logistic Regression": LogisticRegression(max_iter=500, class_weight="balanced", C=0.8, solver="liblinear", random_state=seed),
        "Random Forest": RandomForestClassifier(
            n_estimators=45,
            max_depth=10,
            min_samples_leaf=10,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=seed,
        ),
        "XGBoost": XGBClassifier(
            n_estimators=65,
            max_depth=3,
            learning_rate=0.07,
            subsample=0.86,
            colsample_bytree=0.82,
            min_child_weight=4,
            reg_lambda=1.2,
            objective="binary:logistic",
            eval_metric="logloss",
            n_jobs=4,
            random_state=seed,
        ),
    }


def _metric_values(y_true: np.ndarray, probability: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    prediction = (probability >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, prediction, labels=[0, 1]).ravel()
    roc = roc_auc_score(y_true, probability) if len(np.unique(y_true)) > 1 else float("nan")
    pr = average_precision_score(y_true, probability) if len(np.unique(y_true)) > 1 else float("nan")
    return {
        "roc_auc": float(roc),
        "pr_auc": float(pr),
        "precision": float(precision_score(y_true, prediction, zero_division=0)),
        "recall": float(recall_score(y_true, prediction, zero_division=0)),
        "f1": float(f1_score(y_true, prediction, zero_division=0)),
        "brier": float(brier_score_loss(y_true, probability)),
        "tn": float(tn),
        "fp": float(fp),
        "fn": float(fn),
        "tp": float(tp),
        "positive_rate": float(np.mean(y_true)),
        "predicted_positive_rate": float(np.mean(prediction)),
    }



def _optimal_threshold(y_true: np.ndarray, probability: np.ndarray) -> float:
    best_threshold = 0.5
    best_score = -1.0
    for threshold in np.linspace(0.08, 0.72, 65):
        score = f1_score(y_true, (probability >= threshold).astype(int), zero_division=0)
        if score > best_score:
            best_score = score
            best_threshold = float(threshold)
    return best_threshold

def _temporal_cv(
    X: pd.DataFrame,
    y: pd.Series,
    categorical: list[str],
    numeric: list[str],
    model_name: str,
    estimator: object,
    max_rows: int = 10_000,
) -> list[dict[str, float]]:
    if len(X) > max_rows:
        indexes = np.linspace(0, len(X) - 1, max_rows).astype(int)
        X = X.iloc[indexes].reset_index(drop=True)
        y = y.iloc[indexes].reset_index(drop=True)
    splitter = TimeSeriesSplit(n_splits=3)
    results: list[dict[str, float]] = []
    for fold, (train_index, validation_index) in enumerate(splitter.split(X), start=1):
        if y.iloc[train_index].nunique() < 2 or y.iloc[validation_index].nunique() < 2:
            continue
        pipeline = Pipeline([("preprocessor", _preprocessor(categorical, numeric)), ("model", clone(estimator))])
        pipeline.fit(X.iloc[train_index], y.iloc[train_index])
        probability = pipeline.predict_proba(X.iloc[validation_index])[:, 1]
        metrics = _metric_values(y.iloc[validation_index].to_numpy(), probability)
        metrics["fold"] = float(fold)
        metrics["model_name"] = model_name
        results.append(metrics)
    return results


def _capacity_frame(db_path: str | Path) -> pd.DataFrame:
    frame = read_frame(db_path, "SELECT * FROM DEPARTMENT_DAILY ORDER BY activity_date, department_id")
    frame["activity_date_dt"] = pd.to_datetime(frame["activity_date"])
    frame["day_of_week"] = frame["activity_date_dt"].dt.weekday
    frame["month"] = frame["activity_date_dt"].dt.month
    frame = frame.sort_values(["department_id", "activity_date_dt"])
    frame["lag_1"] = frame.groupby("department_id")["scheduled_appointments"].shift(1)
    frame["lag_7"] = frame.groupby("department_id")["scheduled_appointments"].shift(7)
    frame["rolling_7"] = frame.groupby("department_id")["scheduled_appointments"].transform(lambda s: s.shift(1).rolling(7, min_periods=1).mean())
    frame["rolling_28"] = frame.groupby("department_id")["scheduled_appointments"].transform(lambda s: s.shift(1).rolling(28, min_periods=1).mean())
    frame[["lag_1", "lag_7", "rolling_7", "rolling_28"]] = frame[["lag_1", "lag_7", "rolling_7", "rolling_28"]].fillna(0.0)
    return frame


def _task_data(db_path: str | Path, task_name: str) -> tuple[pd.DataFrame, pd.Series, pd.Series, list[str], list[str], pd.DataFrame]:
    if task_name == "capacity_pressure":
        frame = _capacity_frame(db_path)
        return (
            frame[CAPACITY_CATEGORICAL + CAPACITY_NUMERIC],
            frame["capacity_pressure_label"].astype(int),
            frame["activity_date_dt"],
            CAPACITY_CATEGORICAL,
            CAPACITY_NUMERIC,
            frame,
        )
    frame = read_frame(db_path, "SELECT * FROM APPOINTMENT_FEATURE ORDER BY scheduled_at, appointment_id")
    frame["scheduled_at_dt"] = pd.to_datetime(frame["scheduled_at"])
    target_column = {
        "no_show": "no_show_label",
        "cancellation": "cancellation_label",
        "wait_time_risk": "wait_risk_label",
    }[task_name]
    train_frame = frame[frame[target_column].notna()].copy()
    if task_name == "wait_time_risk":
        train_frame = train_frame[train_frame["total_wait_minutes"].notna()].copy()
    return (
        train_frame[APPOINTMENT_CATEGORICAL + APPOINTMENT_NUMERIC],
        train_frame[target_column].astype(int),
        train_frame["scheduled_at_dt"],
        APPOINTMENT_CATEGORICAL,
        APPOINTMENT_NUMERIC,
        train_frame,
    )


def _risk_band(task: str, probability: float) -> str:
    thresholds = {
        "no_show": (0.12, 0.25, 0.42),
        "cancellation": (0.15, 0.30, 0.48),
        "wait_time_risk": (0.30, 0.50, 0.70),
        "capacity_pressure": (0.30, 0.50, 0.70),
    }[task]
    return "Low" if probability < thresholds[0] else "Moderate" if probability < thresholds[1] else "High" if probability < thresholds[2] else "Critical"


def _decision_support(task: str, band: str) -> str:
    if task == "no_show":
        return "Consider confirmation outreach, a wait-list option, or reminder-channel review." if band in ["High", "Critical"] else "Use standard reminder workflow and monitor confirmation status."
    if task == "cancellation":
        return "Review schedule flexibility and early confirmation; consider wait-list backfill if cancellation occurs." if band in ["High", "Critical"] else "Maintain normal scheduling workflow."
    if task == "wait_time_risk":
        return "Review same-day staffing coverage, queue sequencing and staggered appointment timing." if band in ["High", "Critical"] else "Monitor operational flow against the department wait target."
    return "Review capacity, staffing coverage and appointment-slot distribution for the predicted high-pressure period." if band in ["High", "Critical"] else "Continue routine capacity monitoring."


def _fairness_summary(frame: pd.DataFrame, y_true: pd.Series, probability: np.ndarray, test_index: np.ndarray, task: str) -> list[dict]:
    if task == "capacity_pressure":
        return []
    groups = frame.iloc[test_index][["age_band", "rurality"]].reset_index(drop=True)
    actual = y_true.iloc[test_index].reset_index(drop=True)
    rows: list[dict] = []
    for attribute in ["age_band", "rurality"]:
        for group, indexes in groups.groupby(attribute).groups.items():
            idx = np.array(list(indexes), dtype=int)
            if len(idx) < 20:
                continue
            group_actual = actual.iloc[idx].to_numpy()
            group_probability = probability[idx]
            rows.append(
                {
                    "attribute": attribute,
                    "group": str(group),
                    "n": int(len(idx)),
                    "actual_rate": float(group_actual.mean()),
                    "mean_prediction": float(group_probability.mean()),
                    "brier": float(brier_score_loss(group_actual, group_probability)),
                }
            )
    return rows


def train_models(
    db_path: str | Path,
    bundle_path: str | Path,
    metrics_path: str | Path,
    seed: int = 42,
    manifest_path: str | Path = MANIFEST_PATH,
) -> dict:
    dataset_version = _manifest_version(manifest_path)
    training_date = datetime.now(timezone.utc).isoformat()
    model_version = f"careiq_models_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    tasks = ["no_show", "cancellation", "wait_time_risk", "capacity_pressure"]
    bundle: dict = {
        "model_version": model_version,
        "training_date": training_date,
        "dataset_version": dataset_version,
        "tasks": {},
    }
    metric_rows: list[dict] = []
    registry_rows: list[dict] = []
    metrics_document: dict = {
        "model_version": model_version,
        "training_date": training_date,
        "dataset_version": dataset_version,
        "selection_rule": "Highest mean temporal cross-validation PR-AUC; temporal holdout retained for final evaluation.",
        "tasks": {},
    }

    for task in tasks:
        print(f"  Task: {task}", flush=True)
        X, y, dates, categorical, numeric, full_frame = _task_data(db_path, task)
        order = np.argsort(pd.to_datetime(dates).to_numpy())
        X = X.iloc[order].reset_index(drop=True)
        y = y.iloc[order].reset_index(drop=True)
        dates = pd.Series(pd.to_datetime(dates).iloc[order].to_numpy())
        full_frame = full_frame.iloc[order].reset_index(drop=True)
        if len(X) > 20_000:
            sample_index = np.linspace(0, len(X) - 1, 20_000).astype(int)
            X = X.iloc[sample_index].reset_index(drop=True)
            y = y.iloc[sample_index].reset_index(drop=True)
            dates = dates.iloc[sample_index].reset_index(drop=True)
            full_frame = full_frame.iloc[sample_index].reset_index(drop=True)
        split = max(100, int(len(X) * 0.76))
        split = min(split, len(X) - 50)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]
        candidate_metrics: dict[str, dict] = {}
        fitted_candidates: dict[str, Pipeline] = {}

        for model_name, estimator in _models(seed).items():
            print(f"    Fitting {model_name}", flush=True)
            cv_results = _temporal_cv(X_train, y_train, categorical, numeric, model_name, estimator)
            cv_mean = {
                metric: float(np.nanmean([row[metric] for row in cv_results])) if cv_results else float("nan")
                for metric in ["roc_auc", "pr_auc", "precision", "recall", "f1", "brier"]
            }
            pipeline = Pipeline([("preprocessor", _preprocessor(categorical, numeric)), ("model", estimator)])
            calibration_split = max(100, int(len(X_train) * 0.82))
            calibration_split = min(calibration_split, len(X_train) - 50)
            pipeline.fit(X_train.iloc[:calibration_split], y_train.iloc[:calibration_split])
            calibration_probability = pipeline.predict_proba(X_train.iloc[calibration_split:])[:, 1]
            decision_threshold = _optimal_threshold(y_train.iloc[calibration_split:].to_numpy(), calibration_probability)
            pipeline.fit(X_train, y_train)
            test_probability = pipeline.predict_proba(X_test)[:, 1]
            holdout = _metric_values(y_test.to_numpy(), test_probability, decision_threshold)
            holdout["decision_threshold"] = decision_threshold
            candidate_metrics[model_name] = {"cv_mean": cv_mean, "holdout": holdout, "cv_folds": cv_results, "decision_threshold": decision_threshold}
            fitted_candidates[model_name] = pipeline
            for split_name, metric_map in [("temporal_cv_mean", cv_mean), ("temporal_holdout", holdout)]:
                for metric_name, metric_value in metric_map.items():
                    if not np.isfinite(metric_value):
                        continue
                    metric_rows.append(
                        {
                            "model_version": model_version,
                            "task_name": task,
                            "model_name": model_name,
                            "split_name": split_name,
                            "metric_name": metric_name,
                            "metric_value": float(metric_value),
                        }
                    )

        selected_name = max(candidate_metrics, key=lambda name: np.nan_to_num(candidate_metrics[name]["cv_mean"]["pr_auc"], nan=-1.0))
        selected_pipeline = fitted_candidates[selected_name]
        selected_probability = selected_pipeline.predict_proba(X_test)[:, 1]
        fairness = _fairness_summary(full_frame, y, selected_probability, np.arange(split, len(X)), task) if task != "capacity_pressure" else []
        feature_names = selected_pipeline.named_steps["preprocessor"].get_feature_names_out().tolist()
        bundle["tasks"][task] = {
            "pipeline": selected_pipeline,
            "selected_model": selected_name,
            "categorical_features": categorical,
            "numeric_features": numeric,
            "feature_names": feature_names,
            "train_end": str(dates.iloc[split - 1]),
            "test_start": str(dates.iloc[split]),
            "holdout_rows": int(len(X_test)),
            "decision_threshold": float(candidate_metrics[selected_name]["decision_threshold"]),
        }
        metrics_document["tasks"][task] = {
            "selected_model": selected_name,
            "training_rows": int(len(X_train)),
            "holdout_rows": int(len(X_test)),
            "positive_rate": float(y.mean()),
            "train_end": str(dates.iloc[split - 1]),
            "test_start": str(dates.iloc[split]),
            "candidate_metrics": candidate_metrics,
            "fairness_monitoring": fairness,
        }
        registry_rows.append(
            {
                "model_version": f"{model_version}_{task}",
                "model_name": selected_name,
                "task_name": task,
                "training_date": training_date,
                "dataset_version": dataset_version,
                "selected_flag": 1,
                "feature_count": len(feature_names),
                "temporal_train_end": str(dates.iloc[split - 1]),
                "temporal_test_start": str(dates.iloc[split]),
                "notes": "Operational prediction only; protected demographic fields excluded from model inputs and retained for monitoring.",
            }
        )

    Path(bundle_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, bundle_path, compress=3)
    Path(metrics_path).write_text(json.dumps(metrics_document, indent=2), encoding="utf-8")
    replace_table(db_path, pd.DataFrame(registry_rows), "MODEL_REGISTRY")
    replace_table(db_path, pd.DataFrame(metric_rows), "MODEL_METRIC", chunksize=10_000)
    initialize_predictions(db_path, bundle, dataset_version)
    return metrics_document


def initialize_predictions(db_path: str | Path, bundle: dict, dataset_version: str) -> pd.DataFrame:
    appointment_features = read_frame(db_path, "SELECT * FROM APPOINTMENT_FEATURE WHERE no_show_label IS NULL ORDER BY scheduled_at")
    prediction_rows: list[dict] = []
    timestamp = datetime.now(timezone.utc).isoformat()
    for task in ["no_show", "cancellation", "wait_time_risk"]:
        task_bundle = bundle["tasks"][task]
        columns = task_bundle["categorical_features"] + task_bundle["numeric_features"]
        if appointment_features.empty:
            continue
        probabilities = task_bundle["pipeline"].predict_proba(appointment_features[columns])[:, 1]
        for row, probability in zip(appointment_features.itertuples(index=False), probabilities):
            band = _risk_band(task, float(probability))
            prediction_rows.append(
                {
                    "prediction_id": f"PR_{task}_{row.appointment_id}",
                    "entity_type": "Appointment",
                    "entity_id": row.appointment_id,
                    "task_name": task,
                    "probability": float(probability),
                    "risk_band": band,
                    "prediction_timestamp": timestamp,
                    "model_version": bundle["model_version"],
                    "dataset_version": dataset_version,
                    "top_factor_1": None,
                    "top_factor_2": None,
                    "top_factor_3": None,
                    "decision_support": _decision_support(task, band),
                    "limitations": "Operational probability from synthetic data; not a clinical assessment and not causal evidence.",
                }
            )

    capacity_frame = _capacity_frame(db_path)
    if not capacity_frame.empty:
        latest_dates = capacity_frame["activity_date_dt"].drop_duplicates().sort_values().tail(30)
        recent = capacity_frame[capacity_frame["activity_date_dt"].isin(latest_dates)].copy()
        task_bundle = bundle["tasks"]["capacity_pressure"]
        columns = task_bundle["categorical_features"] + task_bundle["numeric_features"]
        probabilities = task_bundle["pipeline"].predict_proba(recent[columns])[:, 1]
        for row, probability in zip(recent.itertuples(index=False), probabilities):
            band = _risk_band("capacity_pressure", float(probability))
            entity_id = f"{row.department_id}_{row.activity_date}"
            prediction_rows.append(
                {
                    "prediction_id": f"PR_capacity_{entity_id}",
                    "entity_type": "DepartmentDay",
                    "entity_id": entity_id,
                    "task_name": "capacity_pressure",
                    "probability": float(probability),
                    "risk_band": band,
                    "prediction_timestamp": timestamp,
                    "model_version": bundle["model_version"],
                    "dataset_version": dataset_version,
                    "top_factor_1": None,
                    "top_factor_2": None,
                    "top_factor_3": None,
                    "decision_support": _decision_support("capacity_pressure", band),
                    "limitations": "Operational pressure estimate from synthetic capacity and staffing data; not a clinical recommendation.",
                }
            )
    frame = pd.DataFrame(prediction_rows)
    replace_table(db_path, frame, "PREDICTION", chunksize=20_000)
    return frame
