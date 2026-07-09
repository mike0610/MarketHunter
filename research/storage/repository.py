"""
MarketHunter

Module:
Research Repository

Responsibilities:
- Persist virtual research trades in SQLite.
- Restore trades from SQLite into ResearchTrade objects.
- Persist continuous worker status in SQLite.
- Provide open-trade counters and duplicate checks.
- Migrate early MVP database schemas safely.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus


@dataclass(slots=True)
class WorkerStatus:
    """
    Persisted state of the continuous MarketHunter worker.
    """

    state: str
    cycle_number: int

    last_cycle_started_at: datetime | None
    last_cycle_finished_at: datetime | None
    next_cycle_at: datetime | None

    last_error: str | None
    updated_at: datetime


class ResearchRepository:
    """
    SQLite repository for virtual ResearchTrade records
    and continuous worker status.
    """

    OPEN_STATUSES = (
        TradeStatus.WAITING_ENTRY.value,
        TradeStatus.ACTIVE.value,
    )

    DUPLICATE_STATUSES = (
        TradeStatus.CANDIDATE.value,
        TradeStatus.WAITING_ENTRY.value,
        TradeStatus.ACTIVE.value,
    )

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
        self.migrate_schema()

    def create_schema(self) -> None:
        """
        Create SQLite tables used by the research engine.
        """

        with self._lock, self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_trades (
                    id TEXT PRIMARY KEY,
                    signal_id TEXT,
                    symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    probability INTEGER NOT NULL,
                    score REAL NOT NULL,
                    notional REAL NOT NULL DEFAULT 100.0,
                    reasons TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    opened_at TEXT,
                    closed_at TEXT,
                    close_reason TEXT,
                    profit_amount REAL NOT NULL DEFAULT 0.0,
                    profit_percent REAL NOT NULL DEFAULT 0.0,
                    rr REAL NOT NULL DEFAULT 0.0,
                    max_profit_percent REAL NOT NULL DEFAULT 0.0,
                    max_drawdown_percent REAL NOT NULL DEFAULT 0.0,
                    active_candles INTEGER NOT NULL DEFAULT 0,
                    max_active_candles INTEGER NOT NULL DEFAULT 30,
                    last_processed_candle_at TEXT
                )
                """
            )

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_status (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state TEXT NOT NULL,
                    cycle_number INTEGER NOT NULL DEFAULT 0,
                    last_cycle_started_at TEXT,
                    last_cycle_finished_at TEXT,
                    next_cycle_at TEXT,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def migrate_schema(self) -> None:
        """
        Add fields missing from databases created by earlier MVP builds.
        """

        required_columns = {
            "notional": (
                "notional REAL NOT NULL DEFAULT 100.0"
            ),
            "profit_amount": (
                "profit_amount REAL NOT NULL DEFAULT 0.0"
            ),
            "profit_percent": (
                "profit_percent REAL NOT NULL DEFAULT 0.0"
            ),
            "rr": (
                "rr REAL NOT NULL DEFAULT 0.0"
            ),
            "max_profit_percent": (
                "max_profit_percent REAL NOT NULL DEFAULT 0.0"
            ),
            "max_drawdown_percent": (
                "max_drawdown_percent REAL NOT NULL DEFAULT 0.0"
            ),
            "active_candles": (
                "active_candles INTEGER NOT NULL DEFAULT 0"
            ),
            "max_active_candles": (
                "max_active_candles INTEGER NOT NULL DEFAULT 30"
            ),
            "last_processed_candle_at": (
                "last_processed_candle_at TEXT"
            ),
        }

        with self._lock, self.connection:
            rows = self.connection.execute(
                "PRAGMA table_info(research_trades)"
            ).fetchall()

            existing_columns = {
                row["name"]
                for row in rows
            }

            for name, definition in required_columns.items():
                if name not in existing_columns:
                    self.connection.execute(
                        f"""
                        ALTER TABLE research_trades
                        ADD COLUMN {definition}
                        """
                    )

    def save(
        self,
        trade: ResearchTrade,
    ) -> None:
        """
        Insert or update one virtual trade.
        """

        payload = {
            "id": trade.id,
            "signal_id": trade.signal_id,
            "symbol": trade.symbol,
            "market": trade.market,
            "timeframe": trade.timeframe,
            "strategy": trade.strategy,
            "direction": trade.direction,
            "entry_price": trade.entry_price,
            "stop_loss": trade.stop_loss,
            "take_profit": trade.take_profit,
            "probability": trade.probability,
            "score": trade.score,
            "notional": trade.notional,
            "reasons": json.dumps(
                trade.reasons,
                ensure_ascii=False,
            ),
            "status": trade.status.value,
            "created_at": trade.created_at.isoformat(),
            "opened_at": (
                trade.opened_at.isoformat()
                if trade.opened_at
                else None
            ),
            "closed_at": (
                trade.closed_at.isoformat()
                if trade.closed_at
                else None
            ),
            "close_reason": trade.close_reason,
            "profit_amount": trade.profit_amount,
            "profit_percent": trade.profit_percent,
            "rr": trade.rr,
            "max_profit_percent": trade.max_profit_percent,
            "max_drawdown_percent": (
                trade.max_drawdown_percent
            ),
            "active_candles": trade.active_candles,
            "max_active_candles": (
                trade.max_active_candles
            ),
            "last_processed_candle_at": (
                trade.last_processed_candle_at.isoformat()
                if trade.last_processed_candle_at
                else None
            ),
        }

        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO research_trades (
                    id,
                    signal_id,
                    symbol,
                    market,
                    timeframe,
                    strategy,
                    direction,
                    entry_price,
                    stop_loss,
                    take_profit,
                    probability,
                    score,
                    notional,
                    reasons,
                    status,
                    created_at,
                    opened_at,
                    closed_at,
                    close_reason,
                    profit_amount,
                    profit_percent,
                    rr,
                    max_profit_percent,
                    max_drawdown_percent,
                    active_candles,
                    max_active_candles,
                    last_processed_candle_at
                )
                VALUES (
                    :id,
                    :signal_id,
                    :symbol,
                    :market,
                    :timeframe,
                    :strategy,
                    :direction,
                    :entry_price,
                    :stop_loss,
                    :take_profit,
                    :probability,
                    :score,
                    :notional,
                    :reasons,
                    :status,
                    :created_at,
                    :opened_at,
                    :closed_at,
                    :close_reason,
                    :profit_amount,
                    :profit_percent,
                    :rr,
                    :max_profit_percent,
                    :max_drawdown_percent,
                    :active_candles,
                    :max_active_candles,
                    :last_processed_candle_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    signal_id = excluded.signal_id,
                    symbol = excluded.symbol,
                    market = excluded.market,
                    timeframe = excluded.timeframe,
                    strategy = excluded.strategy,
                    direction = excluded.direction,
                    entry_price = excluded.entry_price,
                    stop_loss = excluded.stop_loss,
                    take_profit = excluded.take_profit,
                    probability = excluded.probability,
                    score = excluded.score,
                    notional = excluded.notional,
                    reasons = excluded.reasons,
                    status = excluded.status,
                    opened_at = excluded.opened_at,
                    closed_at = excluded.closed_at,
                    close_reason = excluded.close_reason,
                    profit_amount = excluded.profit_amount,
                    profit_percent = excluded.profit_percent,
                    rr = excluded.rr,
                    max_profit_percent = excluded.max_profit_percent,
                    max_drawdown_percent = (
                        excluded.max_drawdown_percent
                    ),
                    active_candles = excluded.active_candles,
                    max_active_candles = (
                        excluded.max_active_candles
                    ),
                    last_processed_candle_at = (
                        excluded.last_processed_candle_at
                    )
                """,
                payload,
            )

    def save_worker_status(
        self,
        *,
        state: str,
        cycle_number: int,
        last_cycle_started_at: datetime | None,
        last_cycle_finished_at: datetime | None,
        next_cycle_at: datetime | None,
        last_error: str | None,
        updated_at: datetime,
    ) -> None:
        """
        Insert or update the single persisted worker-status record.
        """

        normalized_state = state.strip().lower()

        if not normalized_state:
            raise ValueError(
                "Worker state cannot be empty."
            )

        if cycle_number < 0:
            raise ValueError(
                "Worker cycle number cannot be negative."
            )

        payload = {
            "state": normalized_state,
            "cycle_number": cycle_number,
            "last_cycle_started_at": (
                last_cycle_started_at.isoformat()
                if last_cycle_started_at
                else None
            ),
            "last_cycle_finished_at": (
                last_cycle_finished_at.isoformat()
                if last_cycle_finished_at
                else None
            ),
            "next_cycle_at": (
                next_cycle_at.isoformat()
                if next_cycle_at
                else None
            ),
            "last_error": last_error,
            "updated_at": updated_at.isoformat(),
        }

        with self._lock, self.connection:
            self.connection.execute(
                """
                INSERT INTO worker_status (
                    id,
                    state,
                    cycle_number,
                    last_cycle_started_at,
                    last_cycle_finished_at,
                    next_cycle_at,
                    last_error,
                    updated_at
                )
                VALUES (
                    1,
                    :state,
                    :cycle_number,
                    :last_cycle_started_at,
                    :last_cycle_finished_at,
                    :next_cycle_at,
                    :last_error,
                    :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    state = excluded.state,
                    cycle_number = excluded.cycle_number,
                    last_cycle_started_at = (
                        excluded.last_cycle_started_at
                    ),
                    last_cycle_finished_at = (
                        excluded.last_cycle_finished_at
                    ),
                    next_cycle_at = excluded.next_cycle_at,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                payload,
            )

    def get_worker_status(
        self,
    ) -> WorkerStatus | None:
        """
        Return the latest persisted continuous-worker state.
        """

        with self._lock:
            row = self.connection.execute(
                """
                SELECT *
                FROM worker_status
                WHERE id = 1
                """
            ).fetchone()

        if row is None:
            return None

        return self._row_to_worker_status(
            row=row,
        )

    def get_by_id(
        self,
        trade_id: str,
    ) -> ResearchTrade | None:
        """
        Return one virtual trade by ID.
        """

        with self._lock:
            row = self.connection.execute(
                """
                SELECT *
                FROM research_trades
                WHERE id = ?
                """,
                (trade_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_trade(row)

    def list_all(
        self,
    ) -> list[ResearchTrade]:
        """
        Return all trades, newest first.
        """

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM research_trades
                ORDER BY created_at DESC
                """
            ).fetchall()

        return [
            self._row_to_trade(row)
            for row in rows
        ]

    def list_candidates(
        self,
    ) -> list[ResearchTrade]:
        """
        Return candidate/watchlist trades that can be promoted later.
        """

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM research_trades
                WHERE status = ?
                ORDER BY created_at ASC
                """,
                (
                    TradeStatus.CANDIDATE.value,
                ),
            ).fetchall()

        return [
            self._row_to_trade(row)
            for row in rows
        ]

    def list_open(
        self,
    ) -> list[ResearchTrade]:
        """
        Return trades waiting for entry or currently active.
        """

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM research_trades
                WHERE status IN (?, ?)
                ORDER BY created_at ASC
                """,
                self.OPEN_STATUSES,
            ).fetchall()

        return [
            self._row_to_trade(row)
            for row in rows
        ]

    def count_open_trades(
        self,
    ) -> int:
        """
        Return total count of waiting and active virtual trades.
        """

        with self._lock:
            row = self.connection.execute(
                """
                SELECT COUNT(*) AS trade_count
                FROM research_trades
                WHERE status IN (?, ?)
                """,
                self.OPEN_STATUSES,
            ).fetchone()

        return int(row["trade_count"])

    def count_open_trades_for_symbol(
        self,
        symbol: str,
    ) -> int:
        """
        Return count of open virtual trades for one symbol.

        The limit applies across all strategies, directions and timeframes.
        """

        with self._lock:
            row = self.connection.execute(
                """
                SELECT COUNT(*) AS trade_count
                FROM research_trades
                WHERE UPPER(symbol) = UPPER(?)
                  AND status IN (?, ?)
                """,
                (
                    symbol,
                    *self.OPEN_STATUSES,
                ),
            ).fetchone()

        return int(row["trade_count"])

    def has_open_direction_trade(
        self,
        symbol: str,
        timeframe: str,
        direction: str,
    ) -> bool:
        """
        Return True for an open matching symbol, timeframe and direction.

        Strategy is intentionally excluded from this check. Five strategies
        reporting the same LONG setup must not create five research trades.
        """

        with self._lock:
            row = self.connection.execute(
                """
                SELECT id
                FROM research_trades
                WHERE UPPER(symbol) = UPPER(?)
                  AND timeframe = ?
                  AND UPPER(direction) = UPPER(?)
                  AND status IN (?, ?, ?)
                LIMIT 1
                """,
                (
                    symbol,
                    timeframe,
                    direction,
                    *self.DUPLICATE_STATUSES,
                ),
            ).fetchone()

        return row is not None

    def has_open_trade(
        self,
        symbol: str,
        timeframe: str,
        strategy: str,
        direction: str,
    ) -> bool:
        """
        Compatibility method for older callers.

        Strategy is deliberately ignored. Duplicate control now operates on
        symbol, timeframe and direction only.
        """

        _ = strategy

        return self.has_open_direction_trade(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
        )

    def _row_to_trade(
        self,
        row: sqlite3.Row,
    ) -> ResearchTrade:
        """
        Convert SQLite row into ResearchTrade.
        """

        return ResearchTrade(
            id=row["id"],
            signal_id=row["signal_id"],
            symbol=row["symbol"],
            market=row["market"],
            timeframe=row["timeframe"],
            strategy=row["strategy"],
            direction=row["direction"],
            entry_price=row["entry_price"],
            stop_loss=row["stop_loss"],
            take_profit=row["take_profit"],
            probability=row["probability"],
            score=row["score"],
            notional=row["notional"],
            reasons=json.loads(row["reasons"]),
            status=TradeStatus(row["status"]),
            created_at=datetime.fromisoformat(
                row["created_at"]
            ),
            opened_at=(
                datetime.fromisoformat(row["opened_at"])
                if row["opened_at"]
                else None
            ),
            closed_at=(
                datetime.fromisoformat(row["closed_at"])
                if row["closed_at"]
                else None
            ),
            close_reason=row["close_reason"],
            profit_amount=row["profit_amount"],
            profit_percent=row["profit_percent"],
            rr=row["rr"],
            max_profit_percent=row["max_profit_percent"],
            max_drawdown_percent=row[
                "max_drawdown_percent"
            ],
            active_candles=row["active_candles"],
            max_active_candles=row[
                "max_active_candles"
            ],
            last_processed_candle_at=(
                datetime.fromisoformat(
                    row["last_processed_candle_at"]
                )
                if row["last_processed_candle_at"]
                else None
            ),
        )

    def _row_to_worker_status(
        self,
        row: sqlite3.Row,
    ) -> WorkerStatus:
        """
        Convert SQLite worker-status row into WorkerStatus.
        """

        return WorkerStatus(
            state=row["state"],
            cycle_number=int(row["cycle_number"]),
            last_cycle_started_at=(
                datetime.fromisoformat(
                    row["last_cycle_started_at"]
                )
                if row["last_cycle_started_at"]
                else None
            ),
            last_cycle_finished_at=(
                datetime.fromisoformat(
                    row["last_cycle_finished_at"]
                )
                if row["last_cycle_finished_at"]
                else None
            ),
            next_cycle_at=(
                datetime.fromisoformat(
                    row["next_cycle_at"]
                )
                if row["next_cycle_at"]
                else None
            ),
            last_error=row["last_error"],
            updated_at=datetime.fromisoformat(
                row["updated_at"]
            ),
        )

    def close(self) -> None:
        """
        Close SQLite connection.
        """

        with self._lock:
            self.connection.close()