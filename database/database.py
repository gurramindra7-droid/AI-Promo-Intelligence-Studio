"""SQLite connection handling. One short-lived connection per unit of work (thread-safe enough
for Streamlit + FastAPI background jobs; WAL mode lets readers and a writer work together)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from common.settings import get_settings
from database.models import SCHEMA


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or get_settings().db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


@contextmanager
def session(db_path: str | None = None):
    con = connect(db_path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db(db_path: str | None = None) -> str:
    with session(db_path) as con:
        con.executescript(SCHEMA)
    return db_path or get_settings().db_path


if __name__ == "__main__":
    print("initialised", init_db())
