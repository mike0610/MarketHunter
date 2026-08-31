"""Persistent storage for MarketHunter backtest results."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path("data/backtests.db")


class BacktestRepository:
    def __init__(self, db_path: str | Path | None = None):
        configured = db_path or os.getenv("BACKTEST_DB_PATH") or DEFAULT_DB_PATH
        self.db_path = Path(configured)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_backtest_runs_created_at "
                "ON backtest_runs(created_at DESC)"
            )

    def save(self, record: dict) -> dict:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO backtest_runs (id, label, created_at, result_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["label"],
                    record["created_at"],
                    json.dumps(record["result"], separators=(",", ":")),
                ),
            )
        return record

    def list_recent(self, limit: int = 100) -> list[dict]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, label, created_at, result_json
                FROM backtest_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def get(self, backtest_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, label, created_at, result_json
                FROM backtest_runs
                WHERE id = ?
                """,
                (backtest_id,),
            ).fetchone()
        return self._decode(row) if row is not None else None

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "label": row["label"],
            "created_at": row["created_at"],
            "result": json.loads(row["result_json"]),
        }
