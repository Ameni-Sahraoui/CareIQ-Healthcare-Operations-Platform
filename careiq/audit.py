from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from careiq.database import connect, scalar


def run_consistency_audit(db_path: str | Path, output_path: str | Path) -> dict:
    checks: list[dict] = []

    def add(name: str, passed: bool, value, expectation: str) -> None:
        checks.append({"check": name, "status": "PASS" if passed else "FAIL", "value": value, "expectation": expectation})

    required_tables = [
        "PATIENT", "APPOINTMENT", "DEPARTMENT", "PROVIDER", "FACILITY", "WAIT_TIME", "PATIENT_FLOW",
        "SATISFACTION", "CANCELLATION", "NO_SHOW", "STAFFING", "SERVICE_EVENT", "APPOINTMENT_FEATURE",
        "DEPARTMENT_DAILY", "PREDICTION", "DEMAND_FORECAST", "MODEL_REGISTRY", "MODEL_METRIC",
        "DATA_QUALITY_RESULT", "DECISION_SUPPORT",
    ]
    with connect(db_path) as connection:
        table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        add("Required tables exist", set(required_tables).issubset(table_names), len(set(required_tables) - table_names), "Zero missing required tables")
        for table in required_tables:
            count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if table in table_names else 0
            add(f"{table} populated", count > 0, count, "More than zero rows")

        fk = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        add("Foreign-key integrity", fk == 0, fk, "Zero foreign-key violations")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        add("SQLite integrity", integrity == "ok", integrity, "ok")

        synthetic_failures = 0
        for table in ["PATIENT", "APPOINTMENT", "DEPARTMENT", "PROVIDER", "FACILITY", "WAIT_TIME", "PATIENT_FLOW", "SATISFACTION", "CANCELLATION", "NO_SHOW", "STAFFING", "SERVICE_EVENT"]:
            synthetic_failures += connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE synthetic_record <> 1').fetchone()[0]
        add("Synthetic-data labelling", synthetic_failures == 0, synthetic_failures, "Every record explicitly marked synthetic")

        completed = connection.execute("SELECT COUNT(*) FROM APPOINTMENT WHERE status='Completed'").fetchone()[0]
        flow_coverage = connection.execute("SELECT COUNT(DISTINCT appointment_id) FROM PATIENT_FLOW").fetchone()[0]
        add("Completed appointment to flow coverage", completed == flow_coverage, {"completed": completed, "flow_appointments": flow_coverage}, "One flow record set per completed appointment")

        bad_flow = connection.execute("""
            SELECT COUNT(*) FROM (
                SELECT appointment_id, COUNT(*) AS stages, MIN(stage_order) AS min_stage, MAX(stage_order) AS max_stage
                FROM PATIENT_FLOW GROUP BY appointment_id
            ) WHERE stages <> 8 OR min_stage <> 1 OR max_stage <> 8
        """).fetchone()[0]
        add("Eight-stage patient flow", bad_flow == 0, bad_flow, "Every completed flow has eight ordered stages")

        wait_mismatch = connection.execute("""
            SELECT COUNT(*) FROM WAIT_TIME
            WHERE ABS(total_wait_minutes-(registration_wait_minutes+assessment_wait_minutes+consultation_wait_minutes+diagnostic_service_wait_minutes))>0.05
        """).fetchone()[0]
        add("Wait-time reconciliation", wait_mismatch == 0, wait_mismatch, "Wait total equals components")

        future_appointments = connection.execute("SELECT COUNT(*) FROM APPOINTMENT_FEATURE WHERE no_show_label IS NULL").fetchone()[0]
        for task in ["no_show", "cancellation", "wait_time_risk"]:
            predictions = connection.execute("SELECT COUNT(*) FROM PREDICTION WHERE task_name=? AND entity_type='Appointment'", (task,)).fetchone()[0]
            add(f"Future prediction coverage: {task}", predictions == future_appointments, {"predictions": predictions, "future_appointments": future_appointments}, "One prediction per future appointment")

        bad_probability = connection.execute("SELECT COUNT(*) FROM PREDICTION WHERE probability < 0 OR probability > 1").fetchone()[0]
        add("Prediction probability range", bad_probability == 0, bad_probability, "All probabilities between 0 and 1")

        lineage = connection.execute("""
            SELECT COUNT(*) FROM PREDICTION p
            LEFT JOIN (SELECT DISTINCT substr(model_version,1,instr(model_version||'_','_')-1) AS prefix FROM MODEL_REGISTRY) r ON 1=1
            WHERE p.model_version IS NULL OR p.dataset_version IS NULL OR p.prediction_timestamp IS NULL
        """).fetchone()[0]
        add("Prediction lineage completeness", lineage == 0, lineage, "Model version, dataset version and timestamp populated")

        invalid_intervals = connection.execute("SELECT COUNT(*) FROM DEMAND_FORECAST WHERE lower_bound > forecast_count OR upper_bound < forecast_count OR lower_bound < 0").fetchone()[0]
        add("Forecast interval validity", invalid_intervals == 0, invalid_intervals, "Lower <= forecast <= upper and lower non-negative")

        forecast_dates = connection.execute("SELECT COUNT(DISTINCT forecast_date) FROM DEMAND_FORECAST").fetchone()[0]
        add("Forecast horizon populated", forecast_dates >= 30, forecast_dates, "At least 30 future daily forecast dates")

        high_risk = connection.execute("SELECT COUNT(*) FROM PREDICTION WHERE risk_band IN ('High','Critical')").fetchone()[0]
        recommendations = connection.execute("SELECT COUNT(*) FROM DECISION_SUPPORT WHERE entity_type IN ('Appointment','DepartmentDayForecast','DepartmentDay')").fetchone()[0]
        add("High-risk decision-support coverage", recommendations >= high_risk, {"high_risk": high_risk, "recommendations": recommendations}, "At least one operational recommendation for each high-risk prediction")

        dq_errors = connection.execute("SELECT COUNT(*) FROM DATA_QUALITY_RESULT WHERE stage='clean' AND severity='Error' AND status='FAIL'").fetchone()[0]
        add("Post-clean data quality", dq_errors == 0, dq_errors, "Zero error-severity clean-data failures")

        prohibited = connection.execute("""
            SELECT COUNT(*) FROM DECISION_SUPPORT
            WHERE lower(operational_suggestion) LIKE '%diagnos%'
               OR lower(operational_suggestion) LIKE '%prescrib%'
               OR lower(operational_suggestion) LIKE '%medication%'
        """).fetchone()[0]
        add("Non-clinical recommendation boundary", prohibited == 0, prohibited, "No diagnosis, prescribing or medication language in operational suggestions")

    failures = [check for check in checks if check["status"] == "FAIL"]
    audit = {
        "platform": "CareIQ",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": "PASS" if not failures else "FAIL",
        "checks_passed": len(checks) - len(failures),
        "checks_failed": len(failures),
        "checks": checks,
    }
    Path(output_path).write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit
