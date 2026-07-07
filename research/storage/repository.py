"""
MarketHunter

research/storage/repository.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from research.models.trade import ResearchTrade
from research.models.trade_status import TradeStatus


class ResearchRepository:
    def __init__(
        self,
        path: str = "research.db",
    ) -> None:

        Path(path).touch(exist_ok=True)

        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

        self.create_schema()

    def create_schema(self) -> None:
        cursor = self.connection.cursor()

        cursor.execute(
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
                reasons TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                opened_at TEXT,
                closed_at TEXT,
                close_reason TEXT,
                profit_amount REAL NOT NULL,
                profit_percent REAL NOT NULL,
                rr REAL NOT NULL,
                max_profit_percent REAL NOT NULL,
                max_drawdown_percent REAL NOT NULL
            )
            """
        )

        self.connection.commit()

    def save(
        self,
        trade: ResearchTrade,
    ) -> None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO research_trades (
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
                max_drawdown_percent
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(trade.reasons, ensure_ascii=False),
                trade.status.value,
                trade.created_at.isoformat(),
                trade.opened_at.isoformat() if trade.opened_at else None,
                trade.closed_at.isoformat() if trade.closed_at else None,
                trade.close_reason,
                trade.profit_amount,
                trade.profit_percent,
                trade.rr,
                trade.max_profit_percent,
                trade.max_drawdown_percent,
            ),
        )

        self.connection.commit()

    def list_all(self) -> list[sqlite3.Row]:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM research_trades
            ORDER BY created_at DESC
            """
        )

        return list(cursor.fetchall())

    def list_open(self) -> list[sqlite3.Row]:
        cursor = self.connection.cursor()

        cursor.execute(
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
        )

        return list(cursor.fetchall())

    def close(self) -> None:
        self.connection.close()