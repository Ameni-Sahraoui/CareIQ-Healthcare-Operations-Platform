from __future__ import annotations

from pathlib import Path
import sqlite3
import pandas as pd

from careiq.config import SQL_DIR


def connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path), timeout=120)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA cache_size = -200000")
    return connection


def initialize_database(db_path: str | Path, reset: bool = False) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if reset:
        for candidate in [path, Path(str(path) + "-wal"), Path(str(path) + "-shm")]:
            if candidate.exists():
                candidate.unlink()
    schema = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    with connect(path) as connection:
        connection.executescript(schema)
        connection.commit()


def read_frame(db_path: str | Path, query: str, params: dict | tuple | None = None) -> pd.DataFrame:
    with connect(db_path) as connection:
        return pd.read_sql_query(query, connection, params=params)


def write_frame(
    db_path: str | Path,
    frame: pd.DataFrame,
    table: str,
    if_exists: str = "append",
    index: bool = False,
    chunksize: int = 20_000,
) -> None:
    with connect(db_path) as connection:
        frame.to_sql(table, connection, if_exists=if_exists, index=index, chunksize=chunksize)
        connection.commit()


def replace_table(db_path: str | Path, frame: pd.DataFrame, table: str, chunksize: int = 20_000) -> None:
    with connect(db_path) as connection:
        connection.execute(f'DELETE FROM "{table}"')
        frame.to_sql(table, connection, if_exists="append", index=False, chunksize=chunksize)
        connection.commit()


def scalar(db_path: str | Path, query: str, params: dict | tuple | None = None):
    with connect(db_path) as connection:
        row = connection.execute(query, params or {}) .fetchone()
        return None if row is None else row[0]


def table_count(db_path: str | Path, table: str) -> int:
    return int(scalar(db_path, f'SELECT COUNT(*) FROM "{table}"') or 0)
