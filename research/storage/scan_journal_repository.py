"""
MarketHunter

Module:
Scan Journal Repository

Responsibilities:
- Persist scan runs in SQLite.
- Persist every candidate signal found by Scanner.
- Store rejected, research-qualified and elite signal records.
- Provide scan history for FastAPI and Dashboard.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4


@dataclass(slots=True)
class ScanRun:
    """
    One scanner execution cycle.
    """

    id: str
    started_at: datetime
    finished_at: datetime | None

    status: str

    timeframe: str
    candle_limit: int
    symbol_limit: int
    min_quote_volume_usdt: float

    research_minimum_probability: int
    elite_minimum_probability: int

    symbols_scanned: int
    candidate_signals: int
    research_trades_created: int
    elite_signals_found: int

    error: str | None


@dataclass(slots=True)
class SignalRecord:
    """
    Persisted signal found during one scan run.
    """

    id: str
    scan_run_id: str

    symbol: str
    market: str
    timeframe: str
    strategy: str
    direction: str

    score: float
    probability: int | None
    confidence: str | None

    entry_price: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_reward: float | None

    status: str
    rejected_reason: str | None

    research_trade_id: str | None
    research_skipped: str | None
    is_elite: bool

    reasons: list[str]
    probability_reasons: list[str]
    metadata: dict

    created_at: datetime


class ScanJournalRepository:
    """
    SQLite repository for scan runs and signal records.
    """

    def __init__(
        self,
        path: str = "research.db",
    ) -> None:
        database_path = Path(path)

        database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        database_path.touch(
            exist_ok=True,
        )

        self._lock = RLock()

        self.connection = sqlite3.connect(
            database_path,
            check_same_thread=False,
        )

        self.connection.row_factory = sqlite3.Row

        self.create_schema()

    def create_schema(self) -> None:
        """
        Create scan journal tables.
        """

        with self._lock, self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    candle_limit INTEGER NOT NULL,
                    symbol_limit INTEGER NOT NULL,
                    min_quote_volume_usdt REAL NOT NULL,
                    research_minimum_probability INTEGER NOT NULL,
                    elite_minimum_probability INTEGER NOT NULL,
                    symbols_scanned INTEGER NOT NULL DEFAULT 0,
                    candidate_signals INTEGER NOT NULL DEFAULT 0,
                    research_trades_created INTEGER NOT NULL DEFAULT 0,
                    elite_signals_found INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                )
                """
            )

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_records (
                    id TEXT PRIMARY KEY,
                    scan_run_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    score REAL NOT NULL,
                    probability INTEGER,
                    confidence TEXT,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    risk_reward REAL,
                    status TEXT NOT NULL,
                    rejected_reason TEXT,
                    research_trade_id TEXT,
                    research_skipped TEXT,
                    is_elite INTEGER NOT NULL DEFAULT 0,
                    reasons TEXT NOT NULL,
                    probability_reasons TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(scan_run_id) REFERENCES scan_runs(id)
                )
                """
            )

            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_signal_records_scan_run
                ON signal_records(scan_run_id)
                """
            )

            self.connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_signal_records_status
                ON signal_records(status)
                """
            )

    def create_scan_run(
        self,
        *,
        timeframe: str,
        candle_limit: int,
        symbol_limit: int,
        min_quote_volume_usdt: float,
        research_minimum_probability: int,
        elite_minimum_probability: int,
        started_at: datetime | None = None,
    ) -> ScanRun:
        """
        Create and persist a new scan run.
        """

        normalized_timeframe = timeframe.strip()

        if not normalized_timeframe:
            raise ValueError(
                "Scan run timeframe cannot be empty."
            )

        if candle_limit <= 0:
            raise ValueError(
                "Scan run candle limit must be greater than zero."
            )

        if symbol_limit <= 0:
            raise ValueError(
                "Scan run symbol limit must be greater than zero."
            )

        if min_quote_volume_usdt < 0:
            raise ValueError(
                "Minimum quote volume cannot be negative."
            )

        run = ScanRun(
            id=str(uuid4()),
            started_at=started_at or datetime.now(UTC),
            finished_at=None,
            status="running",
            timeframe=normalized_timeframe,
            candle_limit=candle_limit,
            symbol_limit=symbol_limit,
            min_quote_volume_usdt=min_quote_volume_usdt,
            research_minimum_probability=research_minimum_probability,
            elite_minimum_probability=elite_minimum_probability,
            symbols_scanned=0,
            candidate_signals=0,
            research_trades_created=0,
            elite_signals_found=0,
            error=None,
        )

        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO scan_runs (
                    id,
                    started_at,
                    finished_at,
                    status,
                    timeframe,
                    candle_limit,
                    symbol_limit,
                    min_quote_volume_usdt,
                    research_minimum_probability,
                    elite_minimum_probability,
                    symbols_scanned,
                    candidate_signals,
                    research_trades_created,
                    elite_signals_found,
                    error
                )
                VALUES (
                    :id,
                    :started_at,
                    :finished_at,
                    :status,
                    :timeframe,
                    :candle_limit,
                    :symbol_limit,
                    :min_quote_volume_usdt,
                    :research_minimum_probability,
                    :elite_minimum_probability,
                    :symbols_scanned,
                    :candidate_signals,
                    :research_trades_created,
                    :elite_signals_found,
                    :error
                )
                """,
                self._scan_run_payload(run),
            )

        return run

    def finish_scan_run(
        self,
        *,
        scan_run_id: str,
        status: str,
        symbols_scanned: int,
        candidate_signals: int,
        research_trades_created: int,
        elite_signals_found: int,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> None:
        """
        Mark a scan run as completed or failed.
        """

        normalized_status = status.strip().lower()

        if normalized_status not in {
            "completed",
            "failed",
        }:
            raise ValueError(
                "Scan run status must be completed or failed."
            )

        with self._lock, self.connection:
            self.connection.execute(
                """
                UPDATE scan_runs
                SET
                    finished_at = ?,
                    status = ?,
                    symbols_scanned = ?,
                    candidate_signals = ?,
                    research_trades_created = ?,
                    elite_signals_found = ?,
                    error = ?
                WHERE id = ?
                """,
                (
                    (finished_at or datetime.now(UTC)).isoformat(),
                    normalized_status,
                    symbols_scanned,
                    candidate_signals,
                    research_trades_created,
                    elite_signals_found,
                    error,
                    scan_run_id,
                ),
            )

    def save_signal_record_from_context(
        self,
        *,
        scan_run_id: str,
        context: object,
    ) -> SignalRecord:
        """
        Store a signal record from SignalContext-like object.
        """

        signal = getattr(
            context,
            "signal",
        )

        probability_result = getattr(
            context,
            "probability",
            None,
        )

        risk_result = getattr(
            context,
            "risk",
            None,
        )

        context_metadata = getattr(
            context,
            "metadata",
            {},
        )

        signal_metadata = getattr(
            signal,
            "metadata",
            {},
        )

        accepted = bool(
            getattr(
                context,
                "accepted",
                False,
            )
        )

        rejected_reason = getattr(
            context,
            "rejected_reason",
            None,
        )

        research_trade_id = signal_metadata.get(
            "research_trade_id",
        )

        research_skipped = (
            signal_metadata.get("research_skipped")
            or context_metadata.get("research_skipped")
        )

        is_elite = bool(
            context_metadata.get("elite_signal")
        ) or accepted

        if is_elite:
            record_status = "elite"
        elif research_trade_id:
            record_status = "research"
        else:
            record_status = "rejected"

        probability_reasons = []

        if probability_result is not None:
            probability_reasons = list(
                getattr(
                    probability_result,
                    "reasons",
                    [],
                )
            )

        metadata = {
            **dict(signal_metadata),
            "context_metadata": dict(context_metadata),
        }

        return self.save_signal_record(
            scan_run_id=scan_run_id,
            symbol=signal.symbol,
            market=signal.market,
            timeframe=signal.timeframe,
            strategy=signal.strategy,
            direction=signal.direction,
            score=signal.score,
            probability=(
                getattr(
                    probability_result,
                    "probability",
                    None,
                )
                if probability_result is not None
                else None
            ),
            confidence=(
                str(
                    getattr(
                        probability_result,
                        "confidence",
                        None,
                    )
                )
                if probability_result is not None
                else None
            ),
            entry_price=(
                getattr(
                    risk_result,
                    "entry",
                    None,
                )
                if risk_result is not None
                else None
            ),
            stop_loss=(
                getattr(
                    risk_result,
                    "stop_loss",
                    None,
                )
                if risk_result is not None
                else None
            ),
            take_profit=(
                getattr(
                    risk_result,
                    "take_profit",
                    None,
                )
                if risk_result is not None
                else None
            ),
            risk_reward=(
                getattr(
                    risk_result,
                    "risk_reward",
                    None,
                )
                if risk_result is not None
                else None
            ),
            status=record_status,
            rejected_reason=rejected_reason,
            research_trade_id=research_trade_id,
            research_skipped=research_skipped,
            is_elite=is_elite,
            reasons=list(signal.reasons),
            probability_reasons=probability_reasons,
            metadata=metadata,
        )

    def save_signal_record(
        self,
        *,
        scan_run_id: str,
        symbol: str,
        market: str,
        timeframe: str,
        strategy: str,
        direction: str,
        score: float,
        probability: int | None,
        confidence: str | None,
        entry_price: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        risk_reward: float | None,
        status: str,
        rejected_reason: str | None,
        research_trade_id: str | None,
        research_skipped: str | None,
        is_elite: bool,
        reasons: list[str],
        probability_reasons: list[str],
        metadata: dict,
        created_at: datetime | None = None,
    ) -> SignalRecord:
        """
        Persist one signal record.
        """

        normalized_status = status.strip().lower()

        if normalized_status not in {
            "rejected",
            "research",
            "elite",
        }:
            raise ValueError(
                "Signal record status must be rejected, research or elite."
            )

        record = SignalRecord(
            id=str(uuid4()),
            scan_run_id=scan_run_id,
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            strategy=strategy,
            direction=direction,
            score=float(score),
            probability=probability,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=risk_reward,
            status=normalized_status,
            rejected_reason=rejected_reason,
            research_trade_id=research_trade_id,
            research_skipped=research_skipped,
            is_elite=is_elite,
            reasons=list(reasons),
            probability_reasons=list(probability_reasons),
            metadata=dict(metadata),
            created_at=created_at or datetime.now(UTC),
        )

        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO signal_records (
                    id,
                    scan_run_id,
                    symbol,
                    market,
                    timeframe,
                    strategy,
                    direction,
                    score,
                    probability,
                    confidence,
                    entry_price,
                    stop_loss,
                    take_profit,
                    risk_reward,
                    status,
                    rejected_reason,
                    research_trade_id,
                    research_skipped,
                    is_elite,
                    reasons,
                    probability_reasons,
                    metadata,
                    created_at
                )
                VALUES (
                    :id,
                    :scan_run_id,
                    :symbol,
                    :market,
                    :timeframe,
                    :strategy,
                    :direction,
                    :score,
                    :probability,
                    :confidence,
                    :entry_price,
                    :stop_loss,
                    :take_profit,
                    :risk_reward,
                    :status,
                    :rejected_reason,
                    :research_trade_id,
                    :research_skipped,
                    :is_elite,
                    :reasons,
                    :probability_reasons,
                    :metadata,
                    :created_at
                )
                """,
                self._signal_record_payload(record),
            )

        return record

    def get_latest_scan_run(
        self,
    ) -> ScanRun | None:
        """
        Return latest scan run.
        """

        with self._lock:
            row = self.connection.execute(
                """
                SELECT *
                FROM scan_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None

        return self._row_to_scan_run(row)

    def list_scan_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ScanRun]:
        """
        Return scan runs, newest first.
        """

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM scan_runs
                ORDER BY started_at DESC
                LIMIT ?
                OFFSET ?
                """,
                (
                    limit,
                    offset,
                ),
            ).fetchall()

        return [
            self._row_to_scan_run(row)
            for row in rows
        ]

    def list_signal_records(
        self,
        *,
        scan_run_id: str,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[SignalRecord]:
        """
        Return signal records for one scan run.
        """

        if status:
            normalized_status = status.strip().lower()

            with self._lock:
                rows = self.connection.execute(
                    """
                    SELECT *
                    FROM signal_records
                    WHERE scan_run_id = ?
                      AND status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    OFFSET ?
                    """,
                    (
                        scan_run_id,
                        normalized_status,
                        limit,
                        offset,
                    ),
                ).fetchall()
        else:
            with self._lock:
                rows = self.connection.execute(
                    """
                    SELECT *
                    FROM signal_records
                    WHERE scan_run_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    OFFSET ?
                    """,
                    (
                        scan_run_id,
                        limit,
                        offset,
                    ),
                ).fetchall()

        return [
            self._row_to_signal_record(row)
            for row in rows
        ]

    def count_signal_records(
        self,
        *,
        scan_run_id: str,
        status: str | None = None,
    ) -> int:
        """
        Count signal records for one scan run.
        """

        if status:
            with self._lock:
                row = self.connection.execute(
                    """
                    SELECT COUNT(*) AS record_count
                    FROM signal_records
                    WHERE scan_run_id = ?
                      AND status = ?
                    """,
                    (
                        scan_run_id,
                        status,
                    ),
                ).fetchone()
        else:
            with self._lock:
                row = self.connection.execute(
                    """
                    SELECT COUNT(*) AS record_count
                    FROM signal_records
                    WHERE scan_run_id = ?
                    """,
                    (scan_run_id,),
                ).fetchone()

        return int(row["record_count"])

    def get_signal_record_summary(
        self,
        *,
        scan_run_id: str,
    ) -> dict[str, int]:
        """
        Return signal counts grouped by journal status.
        """

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT status, COUNT(*) AS record_count
                FROM signal_records
                WHERE scan_run_id = ?
                GROUP BY status
                """,
                (scan_run_id,),
            ).fetchall()

        summary = {
            "total": 0,
            "rejected": 0,
            "research": 0,
            "elite": 0,
        }

        for row in rows:
            status = str(row["status"])
            count = int(row["record_count"])

            summary[status] = count
            summary["total"] += count

        return summary

    def _scan_run_payload(
        self,
        run: ScanRun,
    ) -> dict[str, object]:
        """
        Convert ScanRun into SQLite payload.
        """

        return {
            "id": run.id,
            "started_at": run.started_at.isoformat(),
            "finished_at": (
                run.finished_at.isoformat()
                if run.finished_at
                else None
            ),
            "status": run.status,
            "timeframe": run.timeframe,
            "candle_limit": run.candle_limit,
            "symbol_limit": run.symbol_limit,
            "min_quote_volume_usdt": run.min_quote_volume_usdt,
            "research_minimum_probability": (
                run.research_minimum_probability
            ),
            "elite_minimum_probability": (
                run.elite_minimum_probability
            ),
            "symbols_scanned": run.symbols_scanned,
            "candidate_signals": run.candidate_signals,
            "research_trades_created": (
                run.research_trades_created
            ),
            "elite_signals_found": run.elite_signals_found,
            "error": run.error,
        }

    def _signal_record_payload(
        self,
        record: SignalRecord,
    ) -> dict[str, object]:
        """
        Convert SignalRecord into SQLite payload.
        """

        return {
            "id": record.id,
            "scan_run_id": record.scan_run_id,
            "symbol": record.symbol,
            "market": record.market,
            "timeframe": record.timeframe,
            "strategy": record.strategy,
            "direction": record.direction,
            "score": record.score,
            "probability": record.probability,
            "confidence": record.confidence,
            "entry_price": record.entry_price,
            "stop_loss": record.stop_loss,
            "take_profit": record.take_profit,
            "risk_reward": record.risk_reward,
            "status": record.status,
            "rejected_reason": record.rejected_reason,
            "research_trade_id": record.research_trade_id,
            "research_skipped": record.research_skipped,
            "is_elite": int(record.is_elite),
            "reasons": json.dumps(
                record.reasons,
                ensure_ascii=False,
            ),
            "probability_reasons": json.dumps(
                record.probability_reasons,
                ensure_ascii=False,
            ),
            "metadata": json.dumps(
                record.metadata,
                ensure_ascii=False,
                default=str,
            ),
            "created_at": record.created_at.isoformat(),
        }

    def _row_to_scan_run(
        self,
        row: sqlite3.Row,
    ) -> ScanRun:
        """
        Convert SQLite row into ScanRun.
        """

        return ScanRun(
            id=row["id"],
            started_at=datetime.fromisoformat(
                row["started_at"]
            ),
            finished_at=(
                datetime.fromisoformat(
                    row["finished_at"]
                )
                if row["finished_at"]
                else None
            ),
            status=row["status"],
            timeframe=row["timeframe"],
            candle_limit=int(row["candle_limit"]),
            symbol_limit=int(row["symbol_limit"]),
            min_quote_volume_usdt=float(
                row["min_quote_volume_usdt"]
            ),
            research_minimum_probability=int(
                row["research_minimum_probability"]
            ),
            elite_minimum_probability=int(
                row["elite_minimum_probability"]
            ),
            symbols_scanned=int(row["symbols_scanned"]),
            candidate_signals=int(row["candidate_signals"]),
            research_trades_created=int(
                row["research_trades_created"]
            ),
            elite_signals_found=int(
                row["elite_signals_found"]
            ),
            error=row["error"],
        )

    def _row_to_signal_record(
        self,
        row: sqlite3.Row,
    ) -> SignalRecord:
        """
        Convert SQLite row into SignalRecord.
        """

        return SignalRecord(
            id=row["id"],
            scan_run_id=row["scan_run_id"],
            symbol=row["symbol"],
            market=row["market"],
            timeframe=row["timeframe"],
            strategy=row["strategy"],
            direction=row["direction"],
            score=float(row["score"]),
            probability=(
                int(row["probability"])
                if row["probability"] is not None
                else None
            ),
            confidence=row["confidence"],
            entry_price=row["entry_price"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            risk_reward=row["risk_reward"],
            status=row["status"],
            rejected_reason=row["rejected_reason"],
            research_trade_id=row["research_trade_id"],
            research_skipped=row["research_skipped"],
            is_elite=bool(row["is_elite"]),
            reasons=json.loads(row["reasons"]),
            probability_reasons=json.loads(
                row["probability_reasons"]
            ),
            metadata=json.loads(row["metadata"]),
            created_at=datetime.fromisoformat(
                row["created_at"]
            ),
        )

    def close(self) -> None:
        """
        Close SQLite connection.
        """

        with self._lock:
            self.connection.close()