"""Project persistence: SQLite for metadata, the filesystem for big artifacts.

Each project gets a directory under ``data/projects/<id>/`` holding the uploaded
data, the cached posterior draws (``draws.npz``), and generated outputs
(cell-means / trial CSVs, reproducibility report, emitted scripts). Project
metadata and job status live in a small SQLite database so they survive process
restarts and are visible across requests.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional


def _data_dir() -> Path:
    env = os.environ.get("STUDIO_DATA_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent / "data"


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "studio.db"

_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _LOCK, _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                design_json TEXT NOT NULL,
                column_mapping_json TEXT,
                data_rows INTEGER,
                fit_diagnostics_json TEXT,
                fit_error TEXT,
                generation_json TEXT
            )
            """
        )


def project_dir(project_id: str) -> Path:
    d = DATA_DIR / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def create_project(name: str, design: dict[str, Any]) -> str:
    pid = uuid.uuid4().hex[:12]
    ts = _now()
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, created_at, updated_at, "
            "design_json) VALUES (?,?,?,?,?,?)",
            (pid, name, "draft", ts, ts, json.dumps(design)),
        )
    project_dir(pid)
    return pid


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["design"] = json.loads(d.pop("design_json"))
    d["column_mapping"] = json.loads(d.pop("column_mapping_json") or "null")
    d["fit_diagnostics"] = json.loads(d.pop("fit_diagnostics_json") or "null")
    d["generation"] = json.loads(d.pop("generation_json") or "null")
    return d


def get_project(project_id: str) -> Optional[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_projects() -> list[dict[str, Any]]:
    with _LOCK, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _update(project_id: str, **fields: Any) -> None:
    fields["updated_at"] = _now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with _LOCK, _connect() as conn:
        conn.execute(f"UPDATE projects SET {cols} WHERE id=?",
                     (*fields.values(), project_id))


def update_design(project_id: str, design: dict[str, Any]) -> None:
    _update(project_id, design_json=json.dumps(design))


def set_status(project_id: str, status: str, *, fit_error: Optional[str] = None) -> None:
    if fit_error is not None:
        _update(project_id, status=status, fit_error=fit_error)
    else:
        _update(project_id, status=status)


def set_data(project_id: str, n_rows: int, mapping: dict[str, str]) -> None:
    _update(project_id, data_rows=n_rows,
            column_mapping_json=json.dumps(mapping), status="has_data")


def set_fit_result(project_id: str, diagnostics: dict[str, Any]) -> None:
    _update(project_id, status="fitted",
            fit_diagnostics_json=json.dumps(diagnostics), fit_error=None)


def set_generation(project_id: str, generation: dict[str, Any]) -> None:
    _update(project_id, status="generated",
            generation_json=json.dumps(generation))


def delete_project(project_id: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    import shutil
    d = DATA_DIR / "projects" / project_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Artifact paths
# --------------------------------------------------------------------------- #
def data_csv(project_id: str) -> Path:
    return project_dir(project_id) / "data.csv"


def draws_npz(project_id: str) -> Path:
    return project_dir(project_id) / "draws.npz"


def artifact(project_id: str, name: str) -> Path:
    return project_dir(project_id) / name
