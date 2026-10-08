from careiq.database import connect


def test_required_operational_tables_exist_and_are_populated(db_path):
    required = [
        "PATIENT", "APPOINTMENT", "DEPARTMENT", "PROVIDER", "FACILITY", "WAIT_TIME",
        "PATIENT_FLOW", "SATISFACTION", "CANCELLATION", "NO_SHOW", "STAFFING", "SERVICE_EVENT",
    ]
    with connect(db_path) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert set(required).issubset(names)
        for table in required:
            assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] > 0


def test_foreign_keys_and_integrity(db_path):
    with connect(db_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_all_core_records_are_synthetic(db_path):
    tables = ["PATIENT", "APPOINTMENT", "DEPARTMENT", "PROVIDER", "FACILITY", "WAIT_TIME", "PATIENT_FLOW", "SATISFACTION", "CANCELLATION", "NO_SHOW", "STAFFING", "SERVICE_EVENT"]
    with connect(db_path) as connection:
        for table in tables:
            failures = connection.execute(f'SELECT COUNT(*) FROM "{table}" WHERE synthetic_record <> 1').fetchone()[0]
            assert failures == 0


def test_clean_quality_has_no_error_failures(db_path):
    with connect(db_path) as connection:
        failures = connection.execute("SELECT COUNT(*) FROM DATA_QUALITY_RESULT WHERE stage='clean' AND severity='Error' AND status='FAIL'").fetchone()[0]
        assert failures == 0
