from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import argparse
import json

from careiq.audit import run_consistency_audit
from careiq.config import (
    AUDIT_PATH,
    DB_PATH,
    DEMO_CONFIG,
    FULL_CONFIG,
    FORECAST_METRICS_PATH,
    MANIFEST_PATH,
    METRICS_PATH,
    MODEL_BUNDLE_PATH,
    ensure_directories,
)
from careiq.database import initialize_database
from careiq.decisioning import build_decision_support
from careiq.explainability import generate_explanations
from careiq.exports import export_power_bi
from careiq.feature_store import build_feature_store
from careiq.forecasting import train_forecast_model
from careiq.modeling import train_models
from careiq.monitoring import compute_monitoring
from careiq.quality import run_data_quality
from careiq.synthetic import generate_synthetic_data


def bootstrap(
    mode: str = "demo",
    db_path: str | Path = DB_PATH,
    patients: int | None = None,
    appointments: int | None = None,
    seed: int | None = None,
) -> dict:
    ensure_directories()
    config = DEMO_CONFIG if mode == "demo" else FULL_CONFIG
    if patients is not None:
        config = replace(config, n_patients=patients, dataset_name=f"careiq_custom_{patients}_patients")
    if appointments is not None:
        config = replace(config, n_appointments=appointments)
    if seed is not None:
        config = replace(config, seed=seed)
    db_path = Path(db_path)

    print(f"Initializing CareIQ database at {db_path}")
    initialize_database(db_path, reset=True)
    print(f"Generating synthetic healthcare operations data: {config.n_patients:,} patients, {config.n_appointments:,} appointments")
    manifest = generate_synthetic_data(db_path, config, MANIFEST_PATH)
    print("Recording deliberately injected raw-data quality issues")
    raw_quality = run_data_quality(db_path, stage="raw", manifest_path=MANIFEST_PATH)
    print("Validating governed relational data")
    clean_quality = run_data_quality(db_path, stage="clean", manifest_path=MANIFEST_PATH)
    print("Building appointment and department-day analytical feature stores")
    feature_summary = build_feature_store(db_path, MANIFEST_PATH)
    print("Training Logistic Regression, Random Forest and XGBoost classifiers with temporal validation")
    model_metrics = train_models(db_path, MODEL_BUNDLE_PATH, METRICS_PATH, config.seed, MANIFEST_PATH)
    print("Training and evaluating global time-series demand forecasting")
    forecast_metrics = train_forecast_model(db_path, MODEL_BUNDLE_PATH, FORECAST_METRICS_PATH, config.seed, MANIFEST_PATH)
    print("Generating SHAP/global/segment explanations and individual operational factors")
    explanation_summary = generate_explanations(db_path, MODEL_BUNDLE_PATH)
    print("Creating transparent, non-clinical operational decision-support records")
    recommendations = build_decision_support(db_path)
    print("Computing monitoring and drift indicators")
    monitoring = compute_monitoring(db_path, MODEL_BUNDLE_PATH)
    print("Preparing Power BI-ready CSV exports")
    exports = export_power_bi(db_path)
    print("Running end-to-end consistency and safety audit")
    audit = run_consistency_audit(db_path, AUDIT_PATH)

    manifest.update(
        {
            "raw_quality_checks": int(len(raw_quality)),
            "raw_quality_issues": int((raw_quality["failures"] > 0).sum()) if not raw_quality.empty else 0,
            "clean_quality_checks": int(len(clean_quality)),
            "clean_quality_error_failures": int(((clean_quality["severity"] == "Error") & (clean_quality["status"] == "FAIL")).sum()) if not clean_quality.empty else 0,
            "feature_store": feature_summary,
            "model_version": model_metrics["model_version"],
            "selected_models": {task: details["selected_model"] for task, details in model_metrics["tasks"].items()},
            "forecast_model": forecast_metrics["selected_model"],
            "forecast_model_version": forecast_metrics["forecast_model_version"],
            "explanations": explanation_summary,
            "decision_support_rows": int(len(recommendations)),
            "monitoring_rows": int(len(monitoring)),
            "power_bi_exports": exports,
            "consistency_audit_status": audit["overall_status"],
            "consistency_checks_passed": audit["checks_passed"],
            "consistency_checks_failed": audit["checks_failed"],
        }
    )
    Path(MANIFEST_PATH).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"CareIQ bootstrap complete. Audit status: {audit['overall_status']}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="careiq-bootstrap")
    parser.add_argument("--mode", choices=["demo", "full"], default="demo")
    parser.add_argument("--db-path", default=str(DB_PATH))
    parser.add_argument("--patients", type=int)
    parser.add_argument("--appointments", type=int)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    bootstrap(args.mode, args.db_path, args.patients, args.appointments, args.seed)


if __name__ == "__main__":
    main()
