from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from careiq.database import read_frame, replace_table


def build_decision_support(db_path: str | Path) -> pd.DataFrame:
    predictions = read_frame(db_path, "SELECT * FROM PREDICTION")
    rows: list[dict] = []
    created_at = datetime.now(timezone.utc).isoformat()
    high_risk = predictions[predictions["risk_band"].isin(["High", "Critical"])].copy()
    for record in high_risk.itertuples(index=False):
        factors = "; ".join([value for value in [record.top_factor_1, record.top_factor_2, record.top_factor_3] if value])
        evidence = f"{record.task_name} probability {record.probability:.1%}; risk band {record.risk_band}."
        if factors:
            evidence += f" Main model factors: {factors}."
        rows.append(
            {
                "recommendation_id": f"DS_{len(rows)+1:08d}",
                "entity_type": record.entity_type,
                "entity_id": record.entity_id,
                "recommendation_type": record.task_name,
                "evidence": evidence,
                "interpretation": "The model indicates elevated operational risk relative to other synthetic records. This is a prediction, not a causal conclusion.",
                "operational_suggestion": record.decision_support,
                "limitation": record.limitations,
                "created_at": created_at,
            }
        )

    bottlenecks = read_frame(
        db_path,
        """
        SELECT a.department_id, d.department_name, d.facility_id,
               pf.stage_name,
               AVG(pf.queue_minutes) AS avg_queue,
               MAX(pf.queue_minutes) AS max_queue,
               COUNT(*) AS events
        FROM PATIENT_FLOW pf
        JOIN APPOINTMENT a ON pf.appointment_id = a.appointment_id
        JOIN DEPARTMENT d ON a.department_id = d.department_id
        GROUP BY a.department_id, d.department_name, d.facility_id, pf.stage_name
        HAVING COUNT(*) >= 30
        ORDER BY avg_queue DESC
        LIMIT 40
        """,
    )
    for record in bottlenecks.head(20).itertuples(index=False):
        rows.append(
            {
                "recommendation_id": f"DS_{len(rows)+1:08d}",
                "entity_type": "Department",
                "entity_id": record.department_id,
                "recommendation_type": "patient_flow_bottleneck",
                "evidence": f"{record.stage_name} average queue {record.avg_queue:.1f} minutes across {record.events:,} synthetic flow events.",
                "interpretation": "The stage has comparatively high queue time and may be contributing to operational delay.",
                "operational_suggestion": "Review queue sequencing, staffing coverage and hand-off timing at this stage; validate locally before changing operations.",
                "limitation": "Descriptive synthetic-data pattern; it does not establish causation or clinical impact.",
                "created_at": created_at,
            }
        )

    satisfaction = read_frame(
        db_path,
        """
        SELECT d.department_id, d.department_name, COUNT(s.satisfaction_id) AS surveys,
               AVG(s.overall_score) AS satisfaction,
               AVG(w.total_wait_minutes) AS avg_wait
        FROM SATISFACTION s
        JOIN APPOINTMENT a ON s.appointment_id = a.appointment_id
        JOIN DEPARTMENT d ON a.department_id = d.department_id
        LEFT JOIN WAIT_TIME w ON a.appointment_id = w.appointment_id
        GROUP BY d.department_id, d.department_name
        HAVING COUNT(s.satisfaction_id) >= 20
        ORDER BY satisfaction ASC, avg_wait DESC
        LIMIT 15
        """,
    )
    for record in satisfaction.itertuples(index=False):
        rows.append(
            {
                "recommendation_id": f"DS_{len(rows)+1:08d}",
                "entity_type": "Department",
                "entity_id": record.department_id,
                "recommendation_type": "patient_experience_review",
                "evidence": f"Mean satisfaction {record.satisfaction:.2f}/5 from {record.surveys:,} synthetic surveys; average wait {record.avg_wait:.1f} minutes.",
                "interpretation": "Lower experience scores coincide with operational waiting patterns in this synthetic dataset; correlation is not causation.",
                "operational_suggestion": "Review service communication, queue transparency and appointment-flow design with local operational teams.",
                "limitation": "Synthetic survey data and descriptive association only; no clinical inference should be made.",
                "created_at": created_at,
            }
        )

    frame = pd.DataFrame(rows)
    replace_table(db_path, frame, "DECISION_SUPPORT", chunksize=20_000)
    return frame
