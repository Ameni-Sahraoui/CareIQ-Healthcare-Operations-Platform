from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import pandas as pd

from careiq.config import MANIFEST_PATH
from careiq.database import connect, replace_table


def _status(failures: int, severity: str) -> str:
    if failures == 0:
        return "PASS"
    return "WARN" if severity == "Warning" else "FAIL"


def _result(stage: str, entity: str, check: str, severity: str, checked: int, failures: int, details: str) -> dict:
    return {
        "stage": stage,
        "entity_name": entity,
        "check_name": check,
        "severity": severity,
        "records_checked": int(checked),
        "failures": int(failures),
        "status": _status(int(failures), severity),
        "details": details,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _scalar(connection, query: str, params: tuple = ()) -> int | float:
    value = connection.execute(query, params).fetchone()[0]
    return 0 if value is None else value


def run_data_quality(db_path: str | Path, stage: str = "clean", manifest_path: str | Path = MANIFEST_PATH) -> pd.DataFrame:
    results: list[dict] = []
    if stage == "raw":
        manifest_file = Path(manifest_path)
        manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
        issues = manifest.get("injected_raw_issues", [])
        for issue in issues:
            results.append(
                _result(
                    "raw",
                    issue["entity"],
                    issue["issue"],
                    "Warning",
                    issue["count"],
                    issue["count"],
                    "Deliberately injected into transient raw data and repaired during governed ETL.",
                )
            )
    else:
        with connect(db_path) as connection:
            core_tables = [
                "PATIENT", "APPOINTMENT", "DEPARTMENT", "PROVIDER", "FACILITY", "WAIT_TIME",
                "PATIENT_FLOW", "SATISFACTION", "CANCELLATION", "NO_SHOW", "STAFFING", "SERVICE_EVENT",
            ]
            for table in core_tables:
                total = int(_scalar(connection, f'SELECT COUNT(*) FROM "{table}"'))
                duplicates = int(_scalar(connection, f'SELECT COUNT(*) - COUNT(DISTINCT rowid) FROM "{table}"'))
                results.append(_result("clean", table, "Row identity uniqueness", "Error", total, duplicates, "Primary-key and row identity check."))
                synthetic_failures = int(_scalar(connection, f'SELECT COUNT(*) FROM "{table}" WHERE synthetic_record <> 1 OR synthetic_record IS NULL'))
                results.append(_result("clean", table, "Synthetic-data flag", "Error", total, synthetic_failures, "Every operational record must be explicitly labelled synthetic."))

            fk_failures = len(connection.execute("PRAGMA foreign_key_check").fetchall())
            relationship_rows = int(_scalar(connection, "SELECT COUNT(*) FROM APPOINTMENT"))
            results.append(_result("clean", "DATABASE", "Referential integrity", "Error", relationship_rows, fk_failures, "SQLite foreign-key integrity across governed tables."))

            appointment_total = int(_scalar(connection, "SELECT COUNT(*) FROM APPOINTMENT"))
            bad_dates = int(_scalar(connection, "SELECT COUNT(*) FROM APPOINTMENT WHERE datetime(booked_at) >= datetime(scheduled_at)"))
            results.append(_result("clean", "APPOINTMENT", "Booking precedes appointment", "Error", appointment_total, bad_dates, "booked_at must be earlier than scheduled_at."))

            provider_mismatch = int(_scalar(connection, """
                SELECT COUNT(*) FROM APPOINTMENT a
                JOIN PROVIDER p ON a.provider_id = p.provider_id
                WHERE a.department_id <> p.department_id
            """))
            results.append(_result("clean", "APPOINTMENT", "Provider belongs to appointment department", "Error", appointment_total, provider_mismatch, "Prevents cross-department provider key mismatches."))

            facility_mismatch = int(_scalar(connection, """
                SELECT COUNT(*) FROM APPOINTMENT a
                JOIN DEPARTMENT d ON a.department_id = d.department_id
                WHERE a.facility_id <> d.facility_id
            """))
            results.append(_result("clean", "APPOINTMENT", "Facility matches department", "Error", appointment_total, facility_mismatch, "Appointment facility must match its department facility."))

            wait_total = int(_scalar(connection, "SELECT COUNT(*) FROM WAIT_TIME"))
            negative_wait = int(_scalar(connection, """
                SELECT COUNT(*) FROM WAIT_TIME
                WHERE registration_wait_minutes < 0 OR assessment_wait_minutes < 0
                   OR consultation_wait_minutes < 0 OR diagnostic_service_wait_minutes < 0
                   OR total_wait_minutes < 0
            """))
            results.append(_result("clean", "WAIT_TIME", "Non-negative wait durations", "Error", wait_total, negative_wait, "All wait components and totals must be non-negative."))

            wait_reconciliation = int(_scalar(connection, """
                SELECT COUNT(*) FROM WAIT_TIME
                WHERE ABS(total_wait_minutes - (registration_wait_minutes + assessment_wait_minutes + consultation_wait_minutes + diagnostic_service_wait_minutes)) > 0.05
            """))
            results.append(_result("clean", "WAIT_TIME", "Wait component reconciliation", "Error", wait_total, wait_reconciliation, "Total wait must equal the sum of component waits."))

            non_completed_wait = int(_scalar(connection, """
                SELECT COUNT(*) FROM WAIT_TIME w JOIN APPOINTMENT a ON w.appointment_id = a.appointment_id
                WHERE a.status <> 'Completed'
            """))
            results.append(_result("clean", "WAIT_TIME", "Wait records only for completed visits", "Error", wait_total, non_completed_wait, "No-show, cancelled and future scheduled appointments should not have completed-visit wait records."))

            completed_count = int(_scalar(connection, "SELECT COUNT(*) FROM APPOINTMENT WHERE status = 'Completed'"))
            missing_flow = int(_scalar(connection, """
                SELECT COUNT(*) FROM APPOINTMENT a
                LEFT JOIN (SELECT appointment_id, COUNT(*) AS stages FROM PATIENT_FLOW GROUP BY appointment_id) f
                  ON a.appointment_id = f.appointment_id
                WHERE a.status = 'Completed' AND COALESCE(f.stages, 0) <> 8
            """))
            results.append(_result("clean", "PATIENT_FLOW", "Eight-stage operational flow coverage", "Error", completed_count, missing_flow, "Each completed appointment must have the defined eight-stage flow."))

            flow_total = int(_scalar(connection, "SELECT COUNT(*) FROM PATIENT_FLOW"))
            bad_flow_order = int(_scalar(connection, """
                SELECT COUNT(*) FROM PATIENT_FLOW
                WHERE datetime(stage_end) < datetime(stage_start) OR duration_minutes < 0 OR queue_minutes < 0
            """))
            results.append(_result("clean", "PATIENT_FLOW", "Temporal stage validity", "Error", flow_total, bad_flow_order, "Stage end must not precede stage start and durations must be non-negative."))

            sequence_failures = int(_scalar(connection, """
                WITH ordered AS (
                    SELECT appointment_id, stage_order, stage_start, stage_end,
                           LAG(stage_end) OVER (PARTITION BY appointment_id ORDER BY stage_order) AS prior_end
                    FROM PATIENT_FLOW
                )
                SELECT COUNT(*) FROM ordered
                WHERE prior_end IS NOT NULL AND datetime(stage_start) < datetime(prior_end)
            """))
            results.append(_result("clean", "PATIENT_FLOW", "Stage sequence monotonicity", "Error", flow_total, sequence_failures, "A later operational stage cannot start before the prior stage ends."))

            sat_total = int(_scalar(connection, "SELECT COUNT(*) FROM SATISFACTION"))
            bad_scores = int(_scalar(connection, """
                SELECT COUNT(*) FROM SATISFACTION
                WHERE overall_score NOT BETWEEN 1 AND 5 OR service_score NOT BETWEEN 1 AND 5
                   OR communication_score NOT BETWEEN 1 AND 5 OR wait_experience_score NOT BETWEEN 1 AND 5
            """))
            results.append(_result("clean", "SATISFACTION", "Survey score range", "Error", sat_total, bad_scores, "All patient-experience scores must be between 1 and 5."))

            no_show_mismatch = int(_scalar(connection, """
                SELECT COUNT(*) FROM NO_SHOW n JOIN APPOINTMENT a ON n.appointment_id = a.appointment_id
                WHERE a.status <> 'No-Show'
            """))
            no_show_total = int(_scalar(connection, "SELECT COUNT(*) FROM NO_SHOW"))
            results.append(_result("clean", "NO_SHOW", "No-show status consistency", "Error", no_show_total, no_show_mismatch, "NO_SHOW records must reference appointments with No-Show status."))

            cancellation_mismatch = int(_scalar(connection, """
                SELECT COUNT(*) FROM CANCELLATION c JOIN APPOINTMENT a ON c.appointment_id = a.appointment_id
                WHERE a.status <> 'Cancelled' OR datetime(c.cancelled_at) >= datetime(a.scheduled_at)
            """))
            cancellation_total = int(_scalar(connection, "SELECT COUNT(*) FROM CANCELLATION"))
            results.append(_result("clean", "CANCELLATION", "Cancellation timing and status", "Error", cancellation_total, cancellation_mismatch, "Cancellation must occur before the appointment and match Cancelled status."))

            staffing_total = int(_scalar(connection, "SELECT COUNT(*) FROM STAFFING"))
            negative_staffing = int(_scalar(connection, """
                SELECT COUNT(*) FROM STAFFING
                WHERE planned_hours < 0 OR actual_hours < 0 OR required_hours < 0
                   OR overtime_hours < 0 OR absence_hours < 0 OR agency_hours < 0
            """))
            results.append(_result("clean", "STAFFING", "Non-negative staffing hours", "Error", staffing_total, negative_staffing, "Staffing hour measures cannot be negative."))

            future_outcomes = int(_scalar(connection, """
                SELECT COUNT(*) FROM APPOINTMENT
                WHERE date(appointment_date) > date((SELECT MAX(staffing_date) FROM STAFFING)) AND status <> 'Scheduled'
            """))
            future_total = int(_scalar(connection, """
                SELECT COUNT(*) FROM APPOINTMENT
                WHERE date(appointment_date) > date((SELECT MAX(staffing_date) FROM STAFFING))
            """))
            results.append(_result("clean", "APPOINTMENT", "Future appointments remain unlabelled", "Error", future_total, future_outcomes, "Future appointments must remain Scheduled to prevent target leakage."))

    frame = pd.DataFrame(results)
    if frame.empty:
        frame = pd.DataFrame(columns=["stage", "entity_name", "check_name", "severity", "records_checked", "failures", "status", "details", "checked_at"])
    frame.insert(0, "result_id", [f"DQ{index:05d}" for index in range(1, len(frame) + 1)])
    if stage == "clean":
        replace_table(db_path, frame, "DATA_QUALITY_RESULT")
    return frame
