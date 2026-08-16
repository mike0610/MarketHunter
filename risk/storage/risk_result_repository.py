"""
MarketHunter

risk/storage/risk_result_repository.py

Module:
Risk Result Repository

Responsibilities:
- Persist RiskResultRecord history in SQLite, append-only.
- Restore RiskResultRecord instances from SQLite.
- Enforce lineage integrity (first revision, valid supersession).
- Enforce idempotent writes and reject conflicting duplicates.

This is the sole durable-storage owner for RiskResult truth. It
never reads or writes Portfolio or ResearchTrade data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from models.risk_result_record import IdentityState, RiskResultRecord


class RiskResultRepositoryError(Exception):
    """Base error for RiskResultRepository failures."""


class RiskResultConflictError(RiskResultRepositoryError):
    """Same (risk_result_id, revision) already stored with a different record."""


class RiskResultLineageError(RiskResultRepositoryError):
    """Requested append violates append-only lineage rules."""


class RiskResultPersistenceError(RiskResultRepositoryError):
    """Underlying SQLite storage failed."""


_COLUMNS = (
    "risk_result_id",
    "revision",
    "generated_at",
    "supersedes_revision",
    "source_state",
    "source_reference_kind",
    "source_reference",
    "risk_policy_state",
    "risk_policy_version",
    "strategy_name",
    "strategy_version_state",
    "strategy_version",
    "entry",
    "stop_loss",
    "take_profit",
    "risk_reward",
    "position_size",
    "risk_amount",
    "account_size",
    "risk_percent",
)


def _record_to_row(record: RiskResultRecord) -> tuple:
    return (
        record.risk_result_id,
        record.revision,
        record.generated_at.isoformat(),
        record.supersedes_revision,
        record.source_state.value,
        record.source_reference_kind,
        record.source_reference,
        record.risk_policy_state.value,
        record.risk_policy_version,
        record.strategy_name,
        record.strategy_version_state.value,
        record.strategy_version,
        record.entry,
        record.stop_loss,
        record.take_profit,
        record.risk_reward,
        record.position_size,
        record.risk_amount,
        record.account_size,
        record.risk_percent,
    )


def _row_to_record(row: sqlite3.Row) -> RiskResultRecord:
    return RiskResultRecord(
        risk_result_id=row["risk_result_id"],
        revision=row["revision"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
        supersedes_revision=row["supersedes_revision"],
        source_state=IdentityState(row["source_state"]),
        source_reference_kind=row["source_reference_kind"],
        source_reference=row["source_reference"],
        risk_policy_state=IdentityState(row["risk_policy_state"]),
        risk_policy_version=row["risk_policy_version"],
        strategy_name=row["strategy_name"],
        strategy_version_state=IdentityState(row["strategy_version_state"]),
        strategy_version=row["strategy_version"],
        entry=row["entry"],
        stop_loss=row["stop_loss"],
        take_profit=row["take_profit"],
        risk_reward=row["risk_reward"],
        position_size=row["position_size"],
        risk_amount=row["risk_amount"],
        account_size=row["account_size"],
        risk_percent=row["risk_percent"],
    )


class RiskResultRepository:
    """
    SQLite repository for durable, append-only RiskResultRecord
    history.
    """

    def __init__(self, db_path: str | Path) -> None:
        database_path = Path(db_path)

        database_path.parent.mkdir(parents=True, exist_ok=True)
        database_path.touch(exist_ok=True)

        self._lock = RLock()

        self.connection = sqlite3.connect(
            database_path,
            check_same_thread=False,
        )

        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

        self.create_schema()

    def create_schema(self) -> None:
        """
        Create the risk_result_records table if it does not exist.
        """

        with self._lock, self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_result_records (
                    risk_result_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    generated_at TEXT NOT NULL,
                    supersedes_revision INTEGER,
                    source_state TEXT NOT NULL
                        CHECK (source_state IN ('KNOWN', 'UNKNOWN')),
                    source_reference_kind TEXT,
                    source_reference TEXT,
                    risk_policy_state TEXT NOT NULL
                        CHECK (risk_policy_state IN ('KNOWN', 'UNKNOWN')),
                    risk_policy_version TEXT,
                    strategy_name TEXT,
                    strategy_version_state TEXT NOT NULL
                        CHECK (strategy_version_state IN ('KNOWN', 'UNKNOWN')),
                    strategy_version TEXT,
                    entry REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    risk_reward REAL NOT NULL,
                    position_size REAL NOT NULL,
                    risk_amount REAL NOT NULL,
                    account_size REAL NOT NULL,
                    risk_percent REAL NOT NULL,
                    PRIMARY KEY (risk_result_id, revision),
                    FOREIGN KEY (risk_result_id, supersedes_revision)
                        REFERENCES risk_result_records (risk_result_id, revision)
                )
                """
            )

            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_risk_result_records_lineage
                ON risk_result_records (risk_result_id, revision DESC)
                """
            )

    def append_first(self, record: RiskResultRecord) -> RiskResultRecord:
        """
        Append the first revision of a new RiskResultRecord lineage.
        """

        if record.revision != 1:
            raise RiskResultLineageError(
                "append_first requires revision == 1"
            )

        if record.supersedes_revision is not None:
            raise RiskResultLineageError(
                "append_first requires supersedes_revision to be None"
            )

        return self._append(record)

    def append_superseding(self, record: RiskResultRecord) -> RiskResultRecord:
        """
        Append a revision that supersedes an existing revision in the
        same lineage. The predecessor revision must already exist.
        """

        if record.revision <= 1:
            raise RiskResultLineageError(
                "append_superseding requires revision > 1"
            )

        if record.supersedes_revision is None:
            raise RiskResultLineageError(
                "append_superseding requires supersedes_revision to be set"
            )

        if record.supersedes_revision >= record.revision:
            raise RiskResultLineageError(
                "supersedes_revision must be less than revision"
            )

        predecessor = self.get(record.risk_result_id, record.supersedes_revision)

        if predecessor is None:
            raise RiskResultLineageError(
                f"no predecessor {record.risk_result_id}#"
                f"{record.supersedes_revision} in lineage"
            )

        return self._append(record)

    def _append(self, record: RiskResultRecord) -> RiskResultRecord:
        placeholders = ", ".join("?" for _ in _COLUMNS)
        columns_sql = ", ".join(_COLUMNS)

        try:
            with self._lock, self.connection:
                self.connection.execute(
                    f"INSERT INTO risk_result_records ({columns_sql}) "
                    f"VALUES ({placeholders})",
                    _record_to_row(record),
                )
        except sqlite3.IntegrityError:
            existing = self.get(record.risk_result_id, record.revision)

            if existing is not None:
                if existing == record:
                    return existing

                raise RiskResultConflictError(
                    f"{record.risk_result_id}#{record.revision} already "
                    "exists with a different record"
                ) from None

            raise RiskResultLineageError(
                f"insert violates lineage constraints for "
                f"{record.risk_result_id}#{record.revision}"
            ) from None
        except sqlite3.Error as exc:
            raise RiskResultPersistenceError(str(exc)) from exc

        return record

    def get(self, risk_result_id: str, revision: int) -> RiskResultRecord | None:
        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM risk_result_records "
                "WHERE risk_result_id = ? AND revision = ?",
                (risk_result_id, revision),
            )
            row = cursor.fetchone()

        return _row_to_record(row) if row is not None else None

    def get_latest(self, risk_result_id: str) -> RiskResultRecord | None:
        with self._lock:
            cursor = self.connection.execute(
                "SELECT * FROM risk_result_records "
                "WHERE risk_result_id = ? "
                "ORDER BY revision DESC LIMIT 1",
                (risk_result_id,),
            )
            row = cursor.fetchone()

        return _row_to_record(row) if row is not None else None
