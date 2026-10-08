from __future__ import annotations

from pathlib import Path
import pandas as pd

from careiq.config import EXPORT_DIR
from careiq.database import read_frame


def export_power_bi(db_path: str | Path, export_dir: str | Path = EXPORT_DIR) -> dict[str, int]:
    output = Path(export_dir)
    output.mkdir(parents=True, exist_ok=True)
    tables = [
        "FACILITY", "DEPARTMENT", "PROVIDER", "PATIENT", "APPOINTMENT", "WAIT_TIME",
        "PATIENT_FLOW", "SATISFACTION", "CANCELLATION", "NO_SHOW", "STAFFING", "SERVICE_EVENT",
        "DATE_DIMENSION", "APPOINTMENT_FEATURE", "DEPARTMENT_DAILY", "MODEL_REGISTRY", "MODEL_METRIC",
        "PREDICTION", "DEMAND_FORECAST", "GLOBAL_EXPLANATION", "SEGMENT_EXPLANATION",
        "MODEL_MONITORING", "DATA_QUALITY_RESULT", "DECISION_SUPPORT",
    ]
    counts: dict[str, int] = {}
    for table in tables:
        frame = read_frame(db_path, f'SELECT * FROM "{table}"')
        filename = table.lower() + ".csv"
        frame.to_csv(output / filename, index=False)
        counts[filename] = int(len(frame))

    executive = read_frame(
        db_path,
        """
        SELECT
            COUNT(*) AS total_appointments,
            SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) AS completed_appointments,
            SUM(CASE WHEN status='No-Show' THEN 1 ELSE 0 END) AS no_shows,
            SUM(CASE WHEN status='Cancelled' THEN 1 ELSE 0 END) AS cancellations,
            AVG(CASE WHEN status='No-Show' THEN 1.0 ELSE 0.0 END) AS no_show_rate,
            AVG(CASE WHEN status='Cancelled' THEN 1.0 ELSE 0.0 END) AS cancellation_rate
        FROM APPOINTMENT
        """,
    )
    executive.to_csv(output / "executive_kpis.csv", index=False)
    counts["executive_kpis.csv"] = len(executive)

    flow = read_frame(
        db_path,
        """
        SELECT a.department_id, d.department_name, f.facility_name, pf.stage_name,
               COUNT(*) AS stage_events, AVG(pf.queue_minutes) AS average_queue_minutes,
               AVG(pf.duration_minutes) AS average_service_minutes
        FROM PATIENT_FLOW pf
        JOIN APPOINTMENT a ON pf.appointment_id=a.appointment_id
        JOIN DEPARTMENT d ON a.department_id=d.department_id
        JOIN FACILITY f ON a.facility_id=f.facility_id
        GROUP BY a.department_id, d.department_name, f.facility_name, pf.stage_name
        """,
    )
    flow.to_csv(output / "patient_flow_summary.csv", index=False)
    counts["patient_flow_summary.csv"] = len(flow)
    return counts
