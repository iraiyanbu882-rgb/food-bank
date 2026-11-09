from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4


def _database_path() -> Path:
    configured = os.environ.get("RESQNET_DB_PATH")
    return Path(configured) if configured else Path(__file__).resolve().parents[1] / "data" / "resqnet.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    connection = _connect()
    try:
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                kind TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS optimization_results (
                result_id TEXT PRIMARY KEY,
                scenario_name TEXT NOT NULL,
                solver_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                objective_value REAL,
                payload TEXT NOT NULL
            )
            """
        )


def save_dataset(kind: str, payload: Any) -> None:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO datasets(kind, payload) VALUES (?, ?)
            ON CONFLICT(kind) DO UPDATE SET
              payload = excluded.payload,
              updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (kind, encoded),
        )


def save_datasets(datasets: dict[str, Any]) -> None:
    encoded = [
        (kind, json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
        for kind, payload in datasets.items()
    ]
    with _connection() as connection:
        connection.executemany(
            """
            INSERT INTO datasets(kind, payload) VALUES (?, ?)
            ON CONFLICT(kind) DO UPDATE SET
              payload = excluded.payload,
              updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            encoded,
        )


def load_dataset(kind: str) -> Any | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT payload FROM datasets WHERE kind = ?", (kind,)
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def load_all_datasets() -> dict[str, Any]:
    with _connection() as connection:
        rows = connection.execute("SELECT kind, payload FROM datasets").fetchall()
    return {row["kind"]: json.loads(row["payload"]) for row in rows}


def save_result(result: dict[str, Any]) -> None:
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO optimization_results(
                result_id, scenario_name, solver_status, created_at, objective_value, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                result["result_id"],
                result["scenario_name"],
                result["solver_status"],
                result["created_at"],
                result.get("objective_value"),
                json.dumps(result, separators=(",", ":"), ensure_ascii=False),
            ),
        )


def get_result(result_id: str) -> dict[str, Any] | None:
    with _connection() as connection:
        row = connection.execute(
            "SELECT payload FROM optimization_results WHERE result_id = ?",
            (result_id,),
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def list_results(limit: int = 50) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT result_id, scenario_name, solver_status, created_at, objective_value
            FROM optimization_results
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def new_result_id() -> str:
    return str(uuid4())
