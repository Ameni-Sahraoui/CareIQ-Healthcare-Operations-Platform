import json
import joblib
from careiq.database import connect


def test_all_model_families_evaluated(db_path, artifact_paths):
    metrics = json.loads(artifact_paths["metrics"].read_text())
    assert set(metrics["tasks"]) == {"no_show", "cancellation", "wait_time_risk", "capacity_pressure"}
    for task in metrics["tasks"].values():
        assert set(task["candidate_metrics"]) == {"Logistic Regression", "Random Forest", "XGBoost"}
        selected = task["selected_model"]
        assert 0 <= task["candidate_metrics"][selected]["holdout"]["roc_auc"] <= 1
        assert 0 <= task["candidate_metrics"][selected]["holdout"]["pr_auc"] <= 1
        assert 0 < task["candidate_metrics"][selected]["holdout"]["decision_threshold"] < 1


def test_bundle_contains_all_selected_models_and_forecast(artifact_paths):
    bundle = joblib.load(artifact_paths["bundle"])
    assert set(bundle["tasks"]) == {"no_show", "cancellation", "wait_time_risk", "capacity_pressure"}
    assert "forecasting" in bundle
    assert bundle["forecasting"]["model_name"]


def test_prediction_coverage_and_probability_range(db_path):
    with connect(db_path) as connection:
        future = connection.execute("SELECT COUNT(*) FROM APPOINTMENT_FEATURE WHERE no_show_label IS NULL").fetchone()[0]
        for task in ["no_show", "cancellation", "wait_time_risk"]:
            count = connection.execute("SELECT COUNT(*) FROM PREDICTION WHERE task_name=? AND entity_type='Appointment'", (task,)).fetchone()[0]
            assert count == future
        bad = connection.execute("SELECT COUNT(*) FROM PREDICTION WHERE probability < 0 OR probability > 1").fetchone()[0]
        assert bad == 0


def test_forecasts_have_valid_intervals_and_horizon(db_path, artifact_paths):
    forecast_metrics = json.loads(artifact_paths["forecast_metrics"].read_text())
    assert forecast_metrics["forecast_rows"] > 0
    assert forecast_metrics["holdout_interval_coverage"] > 0
    with connect(db_path) as connection:
        bad = connection.execute("SELECT COUNT(*) FROM DEMAND_FORECAST WHERE lower_bound > forecast_count OR upper_bound < forecast_count OR lower_bound < 0").fetchone()[0]
        dates = connection.execute("SELECT COUNT(DISTINCT forecast_date) FROM DEMAND_FORECAST").fetchone()[0]
        assert bad == 0
        assert dates >= 30


def test_explanations_and_nonclinical_decision_support(db_path):
    with connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM GLOBAL_EXPLANATION").fetchone()[0] > 0
        assert connection.execute("SELECT COUNT(*) FROM SEGMENT_EXPLANATION").fetchone()[0] > 0
        assert connection.execute("SELECT COUNT(*) FROM DECISION_SUPPORT").fetchone()[0] > 0
        prohibited = connection.execute("""
            SELECT COUNT(*) FROM DECISION_SUPPORT
            WHERE lower(operational_suggestion) LIKE '%diagnos%'
               OR lower(operational_suggestion) LIKE '%prescrib%'
               OR lower(operational_suggestion) LIKE '%medication%'
        """).fetchone()[0]
        assert prohibited == 0


def test_consistency_audit_passes(artifact_paths):
    audit = json.loads(artifact_paths["audit"].read_text())
    assert audit["overall_status"] == "PASS"
    assert audit["checks_failed"] == 0
