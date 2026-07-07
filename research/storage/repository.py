"""
MarketHunter

Module:
Research Repository

Responsibilities:
- Persist virtual research trades in SQLite.
- Restore trades from SQLite into ResearchTrade objects.
- Migrate early MVP database schemas safely.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import RLock

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus


class ResearchRepository:
    """
    SQLite repository for virtual ResearchTrade records.
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
        self.migrate_schema()

    def create_schema(self) -> None:
        """
        Create database table for virtual research trades.
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
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    max_drawdown_percent = excluded.max_drawdown_percent,
                    active_candles = excluded.active_candles,
                    max_active_candles = excluded.max_active_candles,
                    last_processed_candle_at = (
                        excluded.last_processed_candle_at
                    )
                """,
                (
                    trade.id,
                    trade.signal_id,
                    trade.symbol,
                    trade.market,
                    trade.timeframe,
                    trade.strategy,
                    trade.direction,
                    trade.entry_price,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.probability,
                    trade.score,
                    trade.notional,
                    json.dumps(
                        trade.reasons,
                        ensure_ascii=False,
                    ),
                    trade.status.value,
                    trade.created_at.isoformat(),
                    (
                        trade.opened_at.isoformat()
                        if trade.opened_at
                        else None
                    ),
                    (
                        trade.closed_at.isoformat()
                        if trade.closed_at
                        else None
                    ),
                    trade.close_reason,
                    trade.profit_amount,
                    trade.profit_percent,
                    trade.rr,
                    trade.max_profit_percent,
                    trade.max_drawdown_percent,
                    trade.active_candles,
                    trade.max_active_candles,
                    (
                        trade.last_processed_candle_at.isoformat()
                        if trade.last_processed_candle_at
                        else None
                    ),
                ),
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
                (
                    TradeStatus.WAITING_ENTRY.value,
                    TradeStatus.ACTIVE.value,
                ),
            ).fetchall()

        return [
            self._row_to_trade(row)
            for row in rows
        ]

    def has_open_trade(
        self,
        symbol: str,
        timeframe: str,
        strategy: str,
        direction: str,
    ) -> bool:
        """
        Return True when an equivalent open research trade exists.
        """

        with self._lock:
            row = self.connection.execute(
                """
                SELECT id
                FROM research_trades
                WHERE symbol = ?
                  AND timeframe = ?
                  AND strategy = ?
                  AND direction = ?
                  AND status IN (?, ?)
                LIMIT 1
                """,
                (
                    symbol,
                    timeframe,
                    strategy,
                    direction,
                    TradeStatus.WAITING_ENTRY.value,
                    TradeStatus.ACTIVE.value,
                ),
            ).fetchone()

        return row is not None

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

    def close(self) -> None:
        """
        Close SQLite connection.
        """

        with self._lock:
            self.connection.close()