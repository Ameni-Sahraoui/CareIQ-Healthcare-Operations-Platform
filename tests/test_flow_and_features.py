from careiq.database import connect


def test_completed_appointments_have_eight_ordered_stages(db_path):
    with connect(db_path) as connection:
        completed = connection.execute("SELECT COUNT(*) FROM APPOINTMENT WHERE status='Completed'").fetchone()[0]
        flow_appointments = connection.execute("SELECT COUNT(DISTINCT appointment_id) FROM PATIENT_FLOW").fetchone()[0]
        bad = connection.execute("""
            SELECT COUNT(*) FROM (
                SELECT appointment_id, COUNT(*) AS n, MIN(stage_order) AS lo, MAX(stage_order) AS hi
                FROM PATIENT_FLOW GROUP BY appointment_id
            ) WHERE n <> 8 OR lo <> 1 OR hi <> 8
        """).fetchone()[0]
        assert completed == flow_appointments
        assert bad == 0


def test_wait_components_reconcile(db_path):
    with connect(db_path) as connection:
        bad = connection.execute("""
            SELECT COUNT(*) FROM WAIT_TIME
            WHERE ABS(total_wait_minutes-(registration_wait_minutes+assessment_wait_minutes+consultation_wait_minutes+diagnostic_service_wait_minutes)) > 0.05
        """).fetchone()[0]
        assert bad == 0


def test_feature_store_and_future_labels(db_path):
    with connect(db_path) as connection:
        appointments = connection.execute("SELECT COUNT(*) FROM APPOINTMENT").fetchone()[0]
        features = connection.execute("SELECT COUNT(*) FROM APPOINTMENT_FEATURE").fetchone()[0]
        future = connection.execute("SELECT COUNT(*) FROM APPOINTMENT_FEATURE WHERE no_show_label IS NULL").fetchone()[0]
        future_bad = connection.execute("""
            SELECT COUNT(*) FROM APPOINTMENT_FEATURE af JOIN APPOINTMENT a ON af.appointment_id=a.appointment_id
            WHERE af.no_show_label IS NULL AND a.status <> 'Scheduled'
        """).fetchone()[0]
        assert appointments == features
        assert future > 0
        assert future_bad == 0
