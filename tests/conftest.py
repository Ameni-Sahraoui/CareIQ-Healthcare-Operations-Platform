from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from careiq.config import DB_PATH, MODEL_BUNDLE_PATH, METRICS_PATH, FORECAST_METRICS_PATH, AUDIT_PATH


@pytest.fixture(scope="session")
def db_path():
    assert DB_PATH.exists(), "Packaged demo database is missing"
    return DB_PATH


@pytest.fixture(scope="session")
def artifact_paths():
    return {
        "bundle": MODEL_BUNDLE_PATH,
        "metrics": METRICS_PATH,
        "forecast_metrics": FORECAST_METRICS_PATH,
        "audit": AUDIT_PATH,
    }
