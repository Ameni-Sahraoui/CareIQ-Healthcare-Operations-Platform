from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
ARTIFACT_DIR = ROOT_DIR / "artifacts"
EXPORT_DIR = ROOT_DIR / "exports"
DOCS_DIR = ROOT_DIR / "docs"
SQL_DIR = ROOT_DIR / "sql"
RAW_SAMPLE_DIR = DATA_DIR / "raw_samples"


def resolve_path(value: str | Path, default: Path) -> Path:
    path = Path(value) if value else default
    return path if path.is_absolute() else ROOT_DIR / path


DB_PATH = resolve_path(os.getenv("CAREIQ_DB_PATH", ""), DATA_DIR / "careiq.sqlite")
MODEL_BUNDLE_PATH = resolve_path(os.getenv("CAREIQ_MODEL_BUNDLE", ""), ARTIFACT_DIR / "model_bundle.joblib")
METRICS_PATH = resolve_path(os.getenv("CAREIQ_METRICS", ""), ARTIFACT_DIR / "model_metrics.json")
FORECAST_METRICS_PATH = resolve_path(os.getenv("CAREIQ_FORECAST_METRICS", ""), ARTIFACT_DIR / "forecast_metrics.json")
MANIFEST_PATH = resolve_path(os.getenv("CAREIQ_MANIFEST", ""), ARTIFACT_DIR / "manifest.json")
AUDIT_PATH = resolve_path(os.getenv("CAREIQ_AUDIT", ""), ARTIFACT_DIR / "consistency_audit.json")


@dataclass(frozen=True)
class GenerationConfig:
    n_patients: int = 25_000
    n_appointments: int = 180_000
    facilities_per_province: int = 3
    departments_per_facility: int = 6
    start_date: str = "2023-01-01"
    end_date: str = "2026-12-31"
    as_of_date: str = "2026-11-30"
    forecast_horizon_days: int = 120
    seed: int = 42
    anomaly_rate: float = 0.0015
    dataset_name: str = "careiq_full_synthetic"


DEMO_CONFIG = GenerationConfig(
    n_patients=8_000,
    n_appointments=60_000,
    facilities_per_province=2,
    departments_per_facility=5,
    start_date="2024-01-01",
    end_date="2026-08-31",
    as_of_date="2026-07-31",
    forecast_horizon_days=90,
    seed=42,
    anomaly_rate=0.002,
    dataset_name="careiq_demo_synthetic",
)

FULL_CONFIG = GenerationConfig()


def ensure_directories() -> None:
    for path in [DATA_DIR, ARTIFACT_DIR, EXPORT_DIR, DOCS_DIR, RAW_SAMPLE_DIR]:
        path.mkdir(parents=True, exist_ok=True)
