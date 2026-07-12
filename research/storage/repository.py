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
from research.models.trade_outcome import (
    TradeOutcomeGroup,
    TradeOutcomeType,
    outcome_group_for,
)
from research.models.trade_status import TradeStatus
from research.outcomes import classify_research_trade


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
                    research_group TEXT NOT NULL DEFAULT 'core',
                    experiment_tag TEXT,
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
                    last_processed_candle_at TEXT,
                    outcome_group TEXT NOT NULL DEFAULT 'neutral',
                    outcome_type TEXT NOT NULL DEFAULT 'open_active',
                    outcome_note TEXT,
                    outcome_locked INTEGER NOT NULL DEFAULT 0
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
            "research_group": (
                "research_group TEXT NOT NULL DEFAULT 'core'"
            ),
            "experiment_tag": (
                "experiment_tag TEXT"
            ),
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
            "outcome_group": (
                "outcome_group TEXT NOT NULL DEFAULT 'neutral'"
            ),
            "outcome_type": (
                "outcome_type TEXT NOT NULL DEFAULT 'open_active'"
            ),
            "outcome_note": (
                "outcome_note TEXT"
            ),
            "outcome_locked": (
                "outcome_locked INTEGER NOT NULL DEFAULT 0"
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

            self.connection.execute(
                """
                UPDATE research_trades
                SET
                    research_group = 'experimental',
                    experiment_tag = 'spot_research'
                WHERE LOWER(market) = 'spot'
                  AND (
                      research_group IS NULL
                      OR research_group = ''
                      OR research_group = 'core'
                  )
                """
            )

            self.connection.execute(
                """
                UPDATE research_trades
                SET
                    research_group = 'core',
                    experiment_tag = NULL
                WHERE LOWER(market) != 'spot'
                  AND (
                      research_group IS NULL
                      OR research_group = ''
                  )
                """
            )

        self._backfill_outcome_classification()

    def _backfill_outcome_classification(self) -> None:
        """
        Classify CLOSED/EXPIRED trades still sitting at the
        unclassified default (neutral/open_active, never locked).

        Runs on every startup, not just the first time the
        outcome_group/outcome_type columns are added. The WHERE
        clause scopes this to a handful of rows in the common case
        (nothing to do once every trade has been classified), so this
        stays cheap. Self-healing: if a previous run was interrupted
        between ALTER TABLE and backfill (process killed, disk full),
        the next startup finishes the job instead of leaving those
        trades stuck at the placeholder forever. Never touches a
        manually locked trade (outcome_locked = 1) or lifecycle
        `status`.
        """

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM research_trades
                WHERE status IN (?, ?)
                  AND outcome_locked = 0
                  AND outcome_group = ?
                  AND outcome_type = ?
                """,
                (
                    TradeStatus.CLOSED.value,
                    TradeStatus.EXPIRED.value,
                    TradeOutcomeGroup.NEUTRAL.value,
                    TradeOutcomeType.OPEN_ACTIVE.value,
                ),
            ).fetchall()

        for row in rows:
            trade = self._row_to_trade(row)

            if trade.outcome_locked:
                continue

            outcome_group, outcome_type = (
                classify_research_trade(trade)
            )

            trade.set_outcome(
                outcome_group=outcome_group,
                outcome_type=outcome_type,
            )

            with self._lock, self.connection:
                self.connection.execute(
                    """
                    UPDATE research_trades
                    SET
                        outcome_group = ?,
                        outcome_type = ?,
                        outcome_note = ?
                    WHERE id = ?
                    """,
                    (
                        trade.outcome_group,
                        trade.outcome_type,
                        trade.outcome_note,
                        trade.id,
                    ),
                )

    def save(
        self,
        trade: ResearchTrade,
    ) -> None:
        """
        Insert or update one virtual trade.

        Re-classifies trade.outcome_group / outcome_type on every save
        (research/outcomes.py), unless the trade carries a manual lock
        (trade.outcome_locked) - any manual classification, not just
        excluded, is preserved until include() is called.
        """

        if not trade.outcome_locked:
            outcome_group, outcome_type = (
                classify_research_trade(trade)
            )

            trade.set_outcome(
                outcome_group=outcome_group,
                outcome_type=outcome_type,
            )

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
            "research_group": trade.research_group,
            "experiment_tag": trade.experiment_tag,
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
            "outcome_group": trade.outcome_group,
            "outcome_type": trade.outcome_type,
            "outcome_note": trade.outcome_note,
            "outcome_locked": int(trade.outcome_locked),
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
                    research_group,
                    experiment_tag,
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
                    last_processed_candle_at,
                    outcome_group,
                    outcome_type,
                    outcome_note,
                    outcome_locked
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
                    :research_group,
                    :experiment_tag,
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
                    :last_processed_candle_at,
                    :outcome_group,
                    :outcome_type,
                    :outcome_note,
                    :outcome_locked
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
                    research_group = excluded.research_group,
                    experiment_tag = excluded.experiment_tag,
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
                    ),
                    outcome_group = excluded.outcome_group,
                    outcome_type = excluded.outcome_type,
                    outcome_note = excluded.outcome_note,
                    outcome_locked = excluded.outcome_locked
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

    def list_by_outcome(
        self,
        outcome_group: TradeOutcomeGroup,
    ) -> list[ResearchTrade]:
        """
        Return trades matching one outcome_group, newest first.
        """

        with self._lock:
            rows = self.connection.execute(
                """
                SELECT *
                FROM research_trades
                WHERE outcome_group = ?
                ORDER BY created_at DESC
                """,
                (outcome_group.value,),
            ).fetchall()

        return [
            self._row_to_trade(row)
            for row in rows
        ]

    def set_trade_outcome(
        self,
        trade_id: str,
        outcome_type: TradeOutcomeType,
        note: str | None = None,
    ) -> ResearchTrade | None:
        """
        Manually classify one trade, most commonly to exclude it
        (universe cleanup, invalid legacy data) from clean statistics.

        Returns the updated trade, or None if trade_id was not found.
        This is a manual override: it survives future save() calls
        from the monitor/scanner until restore_trade_outcome() is
        called.
        """

        trade = self.get_by_id(trade_id)

        if trade is None:
            return None

        outcome_group = outcome_group_for(outcome_type)

        trade.set_manual_outcome(
            outcome_group=outcome_group,
            outcome_type=outcome_type,
            note=note,
        )

        with self._lock, self.connection:
            self.connection.execute(
                """
                UPDATE research_trades
                SET
                    outcome_group = ?,
                    outcome_type = ?,
                    outcome_note = ?,
                    outcome_locked = ?
                WHERE id = ?
                """,
                (
                    trade.outcome_group,
                    trade.outcome_type,
                    trade.outcome_note,
                    int(trade.outcome_locked),
                    trade.id,
                ),
            )

        return trade

    def restore_trade_outcome(
        self,
        trade_id: str,
    ) -> ResearchTrade | None:
        """
        Undo a manual set_trade_outcome() / exclude().

        Re-runs automatic classification for this trade's current
        status and persists the result. Returns the updated trade,
        or None if trade_id was not found.
        """

        trade = self.get_by_id(trade_id)

        if trade is None:
            return None

        trade.include()

        self.save(trade)

        return trade

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
        market: str | None = None,
    ) -> int:
        """
        Return count of open virtual trades for one symbol.

        If market is provided, the limit applies to symbol + market.
        The limit applies across all strategies, directions and timeframes.
        """

        normalized_market = (
            market.strip().lower()
            if market
            else None
        )

        with self._lock:
            if normalized_market:
                row = self.connection.execute(
                    """
                    SELECT COUNT(*) AS trade_count
                    FROM research_trades
                    WHERE UPPER(symbol) = UPPER(?)
                      AND LOWER(market) = LOWER(?)
                      AND status IN (?, ?)
                    """,
                    (
                        symbol,
                        normalized_market,
                        *self.OPEN_STATUSES,
                    ),
                ).fetchone()

            else:
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
        timeframe: str | None,
        direction: str,
        market: str | None = None,
    ) -> bool:
        """
        Return True for a duplicate symbol, market and direction.

        Timeframe is accepted for backward compatibility, but duplicate
        protection intentionally ignores timeframe. If ZECUSDT futures LONG
        is already candidate, waiting_entry or active, another ZECUSDT
        futures LONG must not be created from a different timeframe or
        strategy.

        Strategy is intentionally excluded from this check. Five strategies
        reporting the same LONG setup must not create five research trades.
        """

        _ = timeframe

        normalized_market = (
            market.strip().lower()
            if market
            else None
        )

        with self._lock:
            if normalized_market:
                row = self.connection.execute(
                    """
                    SELECT id
                    FROM research_trades
                    WHERE UPPER(symbol) = UPPER(?)
                      AND LOWER(market) = LOWER(?)
                      AND UPPER(direction) = UPPER(?)
                      AND status IN (?, ?, ?)
                    LIMIT 1
                    """,
                    (
                        symbol,
                        normalized_market,
                        direction,
                        *self.DUPLICATE_STATUSES,
                    ),
                ).fetchone()

            else:
                row = self.connection.execute(
                    """
                    SELECT id
                    FROM research_trades
                    WHERE UPPER(symbol) = UPPER(?)
                      AND UPPER(direction) = UPPER(?)
                      AND status IN (?, ?, ?)
                    LIMIT 1
                    """,
                    (
                        symbol,
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
        market: str | None = None,
    ) -> bool:
        """
        Compatibility method for older callers.

        Strategy is deliberately ignored. Duplicate control now operates on
        symbol, market and direction only. Timeframe is accepted for backward
        compatibility but ignored by the duplicate check.
        """

        _ = strategy

        return self.has_open_direction_trade(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            direction=direction,
        )


    def get_direction_conflict_statistics(
        self,
        *,
        limit: int = 2000,
    ) -> dict[str, object]:
        """
        Return direction-conflict analytics from recent signal records.
        """

        def empty_payload() -> dict[str, object]:
            return {
                "summary": {
                    "records": 0,
                    "events": 0,
                    "mixed_rejected": 0,
                    "resolved": 0,
                    "long_winner": 0,
                    "short_winner": 0,
                    "average_delta": 0.0,
                    "average_long_score": 0.0,
                    "average_short_score": 0.0,
                },
                "by_symbol": [],
                "by_strategy": [],
                "by_strategy_pair": [],
                "by_outcome": [],
            }

        def safe_float(value) -> float | None:
            try:
                if value is None:
                    return None

                return float(value)

            except (
                TypeError,
                ValueError,
            ):
                return None

        def safe_list(value) -> list[str]:
            if value is None:
                return []

            if isinstance(value, list):
                return [
                    str(item)
                    for item in value
                    if str(item).strip()
                ]

            return [
                str(value),
            ]

        def format_list(values) -> str:
            clean = sorted(
                {
                    str(item)
                    for item in values
                    if str(item).strip()
                }
            )

            if not clean:
                return "Unknown"

            return ", ".join(clean)

        def new_group(label: str) -> dict[str, object]:
            return {
                "label": label,
                "count": 0,
                "mixed_rejected": 0,
                "resolved": 0,
                "winner": 0,
                "loser_rejected": 0,
                "long_winner": 0,
                "short_winner": 0,
                "symbols": set(),
                "examples": [],
                "_delta_sum": 0.0,
                "_delta_count": 0,
                "_long_score_sum": 0.0,
                "_long_score_count": 0,
                "_short_score_sum": 0.0,
                "_short_score_count": 0,
            }

        def bump_group(
            groups: dict[str, dict[str, object]],
            *,
            label: str,
            symbol: str,
            outcome: str,
            winner_direction: str,
            delta: float | None,
            long_score: float | None,
            short_score: float | None,
            example: str,
        ) -> None:
            group = groups.setdefault(
                label,
                new_group(label),
            )

            group["count"] = int(group["count"]) + 1
            group["symbols"].add(symbol)

            if outcome == "mixed_rejected":
                group["mixed_rejected"] = (
                    int(group["mixed_rejected"])
                    + 1
                )

            if outcome == "resolved":
                group["resolved"] = int(group["resolved"]) + 1

            if outcome == "winner":
                group["winner"] = int(group["winner"]) + 1

            if outcome == "loser_rejected":
                group["loser_rejected"] = (
                    int(group["loser_rejected"])
                    + 1
                )

            if winner_direction == "LONG":
                group["long_winner"] = (
                    int(group["long_winner"])
                    + 1
                )

            if winner_direction == "SHORT":
                group["short_winner"] = (
                    int(group["short_winner"])
                    + 1
                )

            if delta is not None:
                group["_delta_sum"] = (
                    float(group["_delta_sum"])
                    + delta
                )
                group["_delta_count"] = (
                    int(group["_delta_count"])
                    + 1
                )

            if long_score is not None:
                group["_long_score_sum"] = (
                    float(group["_long_score_sum"])
                    + long_score
                )
                group["_long_score_count"] = (
                    int(group["_long_score_count"])
                    + 1
                )

            if short_score is not None:
                group["_short_score_sum"] = (
                    float(group["_short_score_sum"])
                    + short_score
                )
                group["_short_score_count"] = (
                    int(group["_short_score_count"])
                    + 1
                )

            examples = group["examples"]

            if len(examples) < 5:
                examples.append(example)

        def serialize_group(group: dict[str, object]) -> dict[str, object]:
            delta_count = int(group["_delta_count"])
            long_score_count = int(group["_long_score_count"])
            short_score_count = int(group["_short_score_count"])

            return {
                "label": group["label"],
                "count": int(group["count"]),
                "mixed_rejected": int(group["mixed_rejected"]),
                "resolved": int(group["resolved"]),
                "winner": int(group["winner"]),
                "loser_rejected": int(group["loser_rejected"]),
                "long_winner": int(group["long_winner"]),
                "short_winner": int(group["short_winner"]),
                "average_delta": (
                    float(group["_delta_sum"])
                    / delta_count
                    if delta_count > 0
                    else 0.0
                ),
                "average_long_score": (
                    float(group["_long_score_sum"])
                    / long_score_count
                    if long_score_count > 0
                    else 0.0
                ),
                "average_short_score": (
                    float(group["_short_score_sum"])
                    / short_score_count
                    if short_score_count > 0
                    else 0.0
                ),
                "symbols": sorted(group["symbols"]),
                "examples": list(group["examples"]),
            }

        safe_limit = max(
            1,
            min(
                int(limit),
                5000,
            ),
        )

        try:
            with self._lock:
                rows = self.connection.execute(
                    """
                    SELECT
                        scan_run_id,
                        symbol,
                        strategy,
                        direction,
                        status,
                        rejected_reason,
                        metadata
                    FROM signal_records
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (
                        safe_limit,
                    ),
                ).fetchall()

        except sqlite3.OperationalError:
            return empty_payload()

        events: dict[str, dict[str, object]] = {}
        by_strategy: dict[str, dict[str, object]] = {}

        record_count = 0

        for row in rows:
            metadata = self._safe_json_dict(
                row["metadata"],
            )

            if not metadata.get("direction_conflict"):
                continue

            record_count += 1

            symbol = str(
                row["symbol"]
                or metadata.get("conflict_symbol")
                or "Unknown"
            ).upper()

            strategy = str(
                row["strategy"]
                or "Unknown"
            )

            direction = str(
                row["direction"]
                or "Unknown"
            ).upper()

            long_score = safe_float(
                metadata.get("conflict_long_score"),
            )
            short_score = safe_float(
                metadata.get("conflict_short_score"),
            )
            score_delta = safe_float(
                metadata.get("conflict_score_delta"),
            )

            resolution = str(
                metadata.get("conflict_resolution")
                or ""
            )

            signal_outcome = str(
                metadata.get("conflict_signal_outcome")
                or resolution
                or "unknown"
            )

            winner_direction = str(
                metadata.get("conflict_winner_direction")
                or ""
            ).upper()

            scan_run_id = str(
                row["scan_run_id"]
                or "unknown_scan"
            )

            event_key = "|".join(
                [
                    scan_run_id,
                    symbol,
                    str(long_score),
                    str(short_score),
                    str(score_delta),
                ]
            )

            event = events.setdefault(
                event_key,
                {
                    "symbol": symbol,
                    "long_score": long_score,
                    "short_score": short_score,
                    "score_delta": score_delta,
                    "winner_direction": winner_direction,
                    "resolutions": set(),
                    "outcomes": set(),
                    "long_strategies": set(),
                    "short_strategies": set(),
                    "records": 0,
                    "example": "",
                },
            )

            event["records"] = int(event["records"]) + 1
            event["resolutions"].add(resolution)
            event["outcomes"].add(signal_outcome)

            if winner_direction:
                event["winner_direction"] = winner_direction

            event["long_strategies"].update(
                safe_list(
                    metadata.get("conflict_long_strategies"),
                )
            )

            event["short_strategies"].update(
                safe_list(
                    metadata.get("conflict_short_strategies"),
                )
            )

            if direction == "LONG":
                event["long_strategies"].add(strategy)

            if direction == "SHORT":
                event["short_strategies"].add(strategy)

            if not event["example"]:
                event["example"] = (
                    f"{symbol}: LONG {long_score}, "
                    f"SHORT {short_score}, delta {score_delta}"
                )

            bump_group(
                by_strategy,
                label=strategy,
                symbol=symbol,
                outcome=signal_outcome,
                winner_direction=winner_direction,
                delta=score_delta,
                long_score=long_score,
                short_score=short_score,
                example=(
                    f"{symbol} {direction}: {signal_outcome}"
                ),
            )

        if not events:
            payload = empty_payload()
            payload["summary"]["records"] = record_count
            return payload

        by_symbol: dict[str, dict[str, object]] = {}
        by_pair: dict[str, dict[str, object]] = {}
        by_outcome: dict[str, dict[str, object]] = {}

        summary = {
            "records": record_count,
            "events": 0,
            "mixed_rejected": 0,
            "resolved": 0,
            "long_winner": 0,
            "short_winner": 0,
            "_delta_sum": 0.0,
            "_delta_count": 0,
            "_long_score_sum": 0.0,
            "_long_score_count": 0,
            "_short_score_sum": 0.0,
            "_short_score_count": 0,
        }

        for event in events.values():
            resolutions = event["resolutions"]
            outcomes = event["outcomes"]

            if (
                "mixed_rejected" in resolutions
                or "mixed_rejected" in outcomes
            ):
                event_outcome = "mixed_rejected"
            else:
                event_outcome = "resolved"

            symbol = str(event["symbol"])
            winner_direction = str(
                event["winner_direction"]
                or ""
            ).upper()

            long_score = event["long_score"]
            short_score = event["short_score"]
            score_delta = event["score_delta"]

            pair_label = (
                "LONG: "
                f"{format_list(event['long_strategies'])}"
                " | SHORT: "
                f"{format_list(event['short_strategies'])}"
            )

            example = str(
                event["example"]
                or symbol
            )

            summary["events"] = int(summary["events"]) + 1

            if event_outcome == "mixed_rejected":
                summary["mixed_rejected"] = (
                    int(summary["mixed_rejected"])
                    + 1
                )
            else:
                summary["resolved"] = (
                    int(summary["resolved"])
                    + 1
                )

            if winner_direction == "LONG":
                summary["long_winner"] = (
                    int(summary["long_winner"])
                    + 1
                )

            if winner_direction == "SHORT":
                summary["short_winner"] = (
                    int(summary["short_winner"])
                    + 1
                )

            if score_delta is not None:
                summary["_delta_sum"] = (
                    float(summary["_delta_sum"])
                    + float(score_delta)
                )
                summary["_delta_count"] = (
                    int(summary["_delta_count"])
                    + 1
                )

            if long_score is not None:
                summary["_long_score_sum"] = (
                    float(summary["_long_score_sum"])
                    + float(long_score)
                )
                summary["_long_score_count"] = (
                    int(summary["_long_score_count"])
                    + 1
                )

            if short_score is not None:
                summary["_short_score_sum"] = (
                    float(summary["_short_score_sum"])
                    + float(short_score)
                )
                summary["_short_score_count"] = (
                    int(summary["_short_score_count"])
                    + 1
                )

            bump_group(
                by_symbol,
                label=symbol,
                symbol=symbol,
                outcome=event_outcome,
                winner_direction=winner_direction,
                delta=score_delta,
                long_score=long_score,
                short_score=short_score,
                example=example,
            )

            bump_group(
                by_pair,
                label=pair_label,
                symbol=symbol,
                outcome=event_outcome,
                winner_direction=winner_direction,
                delta=score_delta,
                long_score=long_score,
                short_score=short_score,
                example=example,
            )

            bump_group(
                by_outcome,
                label=event_outcome,
                symbol=symbol,
                outcome=event_outcome,
                winner_direction=winner_direction,
                delta=score_delta,
                long_score=long_score,
                short_score=short_score,
                example=example,
            )

        delta_count = int(summary["_delta_count"])
        long_score_count = int(summary["_long_score_count"])
        short_score_count = int(summary["_short_score_count"])

        payload = {
            "summary": {
                "records": int(summary["records"]),
                "events": int(summary["events"]),
                "mixed_rejected": int(summary["mixed_rejected"]),
                "resolved": int(summary["resolved"]),
                "long_winner": int(summary["long_winner"]),
                "short_winner": int(summary["short_winner"]),
                "average_delta": (
                    float(summary["_delta_sum"])
                    / delta_count
                    if delta_count > 0
                    else 0.0
                ),
                "average_long_score": (
                    float(summary["_long_score_sum"])
                    / long_score_count
                    if long_score_count > 0
                    else 0.0
                ),
                "average_short_score": (
                    float(summary["_short_score_sum"])
                    / short_score_count
                    if short_score_count > 0
                    else 0.0
                ),
            },
            "by_symbol": sorted(
                [
                    serialize_group(group)
                    for group in by_symbol.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            )[:20],
            "by_strategy": sorted(
                [
                    serialize_group(group)
                    for group in by_strategy.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            )[:20],
            "by_strategy_pair": sorted(
                [
                    serialize_group(group)
                    for group in by_pair.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            )[:20],
            "by_outcome": sorted(
                [
                    serialize_group(group)
                    for group in by_outcome.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            ),
        }

        return payload


    def get_target_block_statistics(
        self,
        *,
        limit: int = 2000,
    ) -> dict[str, object]:
        """
        Return target-block analytics from recent signal records.
        """

        def empty_payload() -> dict[str, object]:
            return {
                "summary": {
                    "records": 0,
                    "support_blocks": 0,
                    "resistance_blocks": 0,
                    "long_blocks": 0,
                    "short_blocks": 0,
                    "average_distance_to_entry_percent": 0.0,
                    "average_distance_to_target_percent": 0.0,
                },
                "by_symbol": [],
                "by_strategy": [],
                "by_zone_type": [],
                "by_direction": [],
            }

        def safe_float(value) -> float | None:
            try:
                if value is None:
                    return None

                return float(value)

            except (
                TypeError,
                ValueError,
            ):
                return None

        def parse_zone_type(summary: str) -> str:
            normalized = summary.lower()

            if "support zone" in normalized:
                return "support"

            if "resistance zone" in normalized:
                return "resistance"

            return "unknown"

        def parse_zone_center(summary: str) -> float | None:
            normalized = summary.lower()

            if " around " not in normalized:
                return None

            raw = normalized.split(
                " around ",
                1,
            )[1].strip()

            raw = raw.split()[0].strip().rstrip(".")

            return safe_float(raw)

        def is_target_block(row, metadata: dict[str, object]) -> bool:
            reason = str(
                row["research_skipped"]
                or row["rejected_reason"]
                or metadata.get("research_skipped")
                or metadata.get("target_summary")
                or ""
            ).lower()

            if metadata.get("target_clear") is False:
                return True

            return (
                "target quality" in reason
                or "blocked by support" in reason
                or "blocked by resistance" in reason
                or "tp 1:3 is blocked" in reason
            )

        def new_group(label: str) -> dict[str, object]:
            return {
                "label": label,
                "count": 0,
                "support_blocks": 0,
                "resistance_blocks": 0,
                "long_blocks": 0,
                "short_blocks": 0,
                "symbols": set(),
                "strategies": {},
                "examples": [],
                "_target_rr_sum": 0.0,
                "_target_rr_count": 0,
                "_zone_center_sum": 0.0,
                "_zone_center_count": 0,
                "_distance_entry_sum": 0.0,
                "_distance_entry_count": 0,
                "_distance_target_sum": 0.0,
                "_distance_target_count": 0,
            }

        def bump_count_map(value: dict[str, int], key: str) -> None:
            value[key] = int(
                value.get(
                    key,
                    0,
                )
            ) + 1

        def bump_group(
            groups: dict[str, dict[str, object]],
            *,
            label: str,
            symbol: str,
            strategy: str,
            direction: str,
            zone_type: str,
            target_rr: float | None,
            zone_center: float | None,
            distance_entry: float | None,
            distance_target: float | None,
            example: str,
        ) -> None:
            group = groups.setdefault(
                label,
                new_group(label),
            )

            group["count"] = int(group["count"]) + 1
            group["symbols"].add(symbol)
            bump_count_map(
                group["strategies"],
                strategy,
            )

            if zone_type == "support":
                group["support_blocks"] = (
                    int(group["support_blocks"])
                    + 1
                )

            if zone_type == "resistance":
                group["resistance_blocks"] = (
                    int(group["resistance_blocks"])
                    + 1
                )

            if direction == "LONG":
                group["long_blocks"] = (
                    int(group["long_blocks"])
                    + 1
                )

            if direction == "SHORT":
                group["short_blocks"] = (
                    int(group["short_blocks"])
                    + 1
                )

            if target_rr is not None:
                group["_target_rr_sum"] = (
                    float(group["_target_rr_sum"])
                    + target_rr
                )
                group["_target_rr_count"] = (
                    int(group["_target_rr_count"])
                    + 1
                )

            if zone_center is not None:
                group["_zone_center_sum"] = (
                    float(group["_zone_center_sum"])
                    + zone_center
                )
                group["_zone_center_count"] = (
                    int(group["_zone_center_count"])
                    + 1
                )

            if distance_entry is not None:
                group["_distance_entry_sum"] = (
                    float(group["_distance_entry_sum"])
                    + distance_entry
                )
                group["_distance_entry_count"] = (
                    int(group["_distance_entry_count"])
                    + 1
                )

            if distance_target is not None:
                group["_distance_target_sum"] = (
                    float(group["_distance_target_sum"])
                    + distance_target
                )
                group["_distance_target_count"] = (
                    int(group["_distance_target_count"])
                    + 1
                )

            examples = group["examples"]

            if len(examples) < 5:
                examples.append(example)

        def serialize_group(group: dict[str, object]) -> dict[str, object]:
            target_rr_count = int(group["_target_rr_count"])
            zone_center_count = int(group["_zone_center_count"])
            distance_entry_count = int(group["_distance_entry_count"])
            distance_target_count = int(group["_distance_target_count"])

            return {
                "label": group["label"],
                "count": int(group["count"]),
                "support_blocks": int(group["support_blocks"]),
                "resistance_blocks": int(group["resistance_blocks"]),
                "long_blocks": int(group["long_blocks"]),
                "short_blocks": int(group["short_blocks"]),
                "average_target_rr": (
                    float(group["_target_rr_sum"])
                    / target_rr_count
                    if target_rr_count > 0
                    else 0.0
                ),
                "average_zone_center": (
                    float(group["_zone_center_sum"])
                    / zone_center_count
                    if zone_center_count > 0
                    else 0.0
                ),
                "average_distance_to_entry_percent": (
                    float(group["_distance_entry_sum"])
                    / distance_entry_count
                    if distance_entry_count > 0
                    else 0.0
                ),
                "average_distance_to_target_percent": (
                    float(group["_distance_target_sum"])
                    / distance_target_count
                    if distance_target_count > 0
                    else 0.0
                ),
                "symbols": sorted(group["symbols"]),
                "strategies": dict(
                    sorted(
                        group["strategies"].items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                ),
                "examples": list(group["examples"]),
            }

        safe_limit = max(
            1,
            min(
                int(limit),
                5000,
            ),
        )

        try:
            with self._lock:
                rows = self.connection.execute(
                    """
                    SELECT
                        symbol,
                        strategy,
                        direction,
                        rejected_reason,
                        research_skipped,
                        metadata
                    FROM signal_records
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (
                        safe_limit,
                    ),
                ).fetchall()

        except sqlite3.OperationalError:
            return empty_payload()

        summary = {
            "records": 0,
            "support_blocks": 0,
            "resistance_blocks": 0,
            "long_blocks": 0,
            "short_blocks": 0,
            "_distance_entry_sum": 0.0,
            "_distance_entry_count": 0,
            "_distance_target_sum": 0.0,
            "_distance_target_count": 0,
        }

        by_symbol: dict[str, dict[str, object]] = {}
        by_strategy: dict[str, dict[str, object]] = {}
        by_zone_type: dict[str, dict[str, object]] = {}
        by_direction: dict[str, dict[str, object]] = {}

        for row in rows:
            metadata = self._safe_json_dict(
                row["metadata"],
            )

            if not is_target_block(
                row,
                metadata,
            ):
                continue

            symbol = str(
                row["symbol"]
                or "Unknown"
            ).upper()

            strategy = str(
                row["strategy"]
                or "Unknown"
            )

            direction = str(
                row["direction"]
                or "Unknown"
            ).upper()

            target_summary = str(
                metadata.get("target_summary")
                or row["research_skipped"]
                or row["rejected_reason"]
                or ""
            )

            zone_type = str(
                metadata.get("target_blocking_zone_type")
                or parse_zone_type(target_summary)
                or "unknown"
            ).lower()

            target_rr = safe_float(
                metadata.get("target_rr"),
            )

            zone_center = safe_float(
                metadata.get("target_blocking_zone_center"),
            )

            if zone_center is None:
                zone_center = parse_zone_center(
                    target_summary,
                )

            distance_entry = safe_float(
                metadata.get(
                    "target_blocking_zone_distance_to_entry_percent",
                ),
            )

            distance_target = safe_float(
                metadata.get(
                    "target_blocking_zone_distance_to_target_percent",
                ),
            )

            example = (
                f"{symbol} {direction} {strategy}: "
                f"{target_summary}"
            )

            summary["records"] = int(summary["records"]) + 1

            if zone_type == "support":
                summary["support_blocks"] = (
                    int(summary["support_blocks"])
                    + 1
                )

            if zone_type == "resistance":
                summary["resistance_blocks"] = (
                    int(summary["resistance_blocks"])
                    + 1
                )

            if direction == "LONG":
                summary["long_blocks"] = (
                    int(summary["long_blocks"])
                    + 1
                )

            if direction == "SHORT":
                summary["short_blocks"] = (
                    int(summary["short_blocks"])
                    + 1
                )

            if distance_entry is not None:
                summary["_distance_entry_sum"] = (
                    float(summary["_distance_entry_sum"])
                    + distance_entry
                )
                summary["_distance_entry_count"] = (
                    int(summary["_distance_entry_count"])
                    + 1
                )

            if distance_target is not None:
                summary["_distance_target_sum"] = (
                    float(summary["_distance_target_sum"])
                    + distance_target
                )
                summary["_distance_target_count"] = (
                    int(summary["_distance_target_count"])
                    + 1
                )

            for groups, label in [
                (by_symbol, symbol),
                (by_strategy, strategy),
                (by_zone_type, zone_type),
                (by_direction, direction),
            ]:
                bump_group(
                    groups,
                    label=label,
                    symbol=symbol,
                    strategy=strategy,
                    direction=direction,
                    zone_type=zone_type,
                    target_rr=target_rr,
                    zone_center=zone_center,
                    distance_entry=distance_entry,
                    distance_target=distance_target,
                    example=example,
                )

        distance_entry_count = int(summary["_distance_entry_count"])
        distance_target_count = int(summary["_distance_target_count"])

        return {
            "summary": {
                "records": int(summary["records"]),
                "support_blocks": int(summary["support_blocks"]),
                "resistance_blocks": int(summary["resistance_blocks"]),
                "long_blocks": int(summary["long_blocks"]),
                "short_blocks": int(summary["short_blocks"]),
                "average_distance_to_entry_percent": (
                    float(summary["_distance_entry_sum"])
                    / distance_entry_count
                    if distance_entry_count > 0
                    else 0.0
                ),
                "average_distance_to_target_percent": (
                    float(summary["_distance_target_sum"])
                    / distance_target_count
                    if distance_target_count > 0
                    else 0.0
                ),
            },
            "by_symbol": sorted(
                [
                    serialize_group(group)
                    for group in by_symbol.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            )[:20],
            "by_strategy": sorted(
                [
                    serialize_group(group)
                    for group in by_strategy.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            )[:20],
            "by_zone_type": sorted(
                [
                    serialize_group(group)
                    for group in by_zone_type.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            ),
            "by_direction": sorted(
                [
                    serialize_group(group)
                    for group in by_direction.values()
                ],
                key=lambda item: int(item["count"]),
                reverse=True,
            ),
        }


    def get_signal_block_reason_statistics(
        self,
        *,
        limit: int = 1000,
    ) -> list[dict[str, object]]:
        """
        Return recent scan-journal rejection/block statistics.

        This reads signal_records from the same SQLite database. If the
        scan-journal table has not been created yet, an empty list is returned.
        """

        safe_limit = max(
            1,
            min(
                int(limit),
                5000,
            ),
        )

        try:
            with self._lock:
                rows = self.connection.execute(
                    """
                    SELECT
                        strategy,
                        direction,
                        status,
                        rejected_reason,
                        research_skipped,
                        reasons,
                        probability_reasons,
                        metadata
                    FROM signal_records
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (
                        safe_limit,
                    ),
                ).fetchall()

        except sqlite3.OperationalError:
            return []

        groups: dict[str, dict[str, object]] = {}

        for row in rows:
            metadata = self._safe_json_dict(
                row["metadata"],
            )

            reason = (
                row["research_skipped"]
                or row["rejected_reason"]
                or metadata.get("research_skipped")
                or metadata.get("elite_skipped")
                or "Unknown"
            )

            label = self._signal_block_reason_key(
                str(reason),
            )

            if label not in groups:
                groups[label] = {
                    "label": label,
                    "count": 0,
                    "strategies": {},
                    "directions": {},
                    "examples": [],
                }

            group = groups[label]
            group["count"] = int(group["count"]) + 1

            strategy = str(
                row["strategy"]
                or "Unknown"
            )

            direction = str(
                row["direction"]
                or "Unknown"
            ).upper()

            strategies = group["strategies"]
            directions = group["directions"]

            strategies[strategy] = int(
                strategies.get(
                    strategy,
                    0,
                )
            ) + 1

            directions[direction] = int(
                directions.get(
                    direction,
                    0,
                )
            ) + 1

            examples = group["examples"]

            if len(examples) < 5:
                examples.append(
                    str(reason),
                )

        result = list(
            groups.values()
        )

        result.sort(
            key=lambda item: int(
                item["count"],
            ),
            reverse=True,
        )

        return result

    @staticmethod
    def _safe_json_dict(
        value,
    ) -> dict:
        if not value:
            return {}

        if isinstance(value, dict):
            return value

        try:
            decoded = json.loads(value)
        except Exception:
            return {}

        if isinstance(decoded, dict):
            return decoded

        return {}

    @staticmethod
    def _signal_block_reason_key(
        reason: str,
    ) -> str:
        normalized = reason.lower()

        if "risk geometry" in normalized:
            return "Risk geometry blocked"

        if "target quality" in normalized or "blocked by support" in normalized or "blocked by resistance" in normalized:
            return "Target blocked"

        if "reaction quality" in normalized or "no confirmed reaction" in normalized:
            return "Reaction blocked"

        if "parabolic" in normalized:
            return "Parabolic blocked"

        if "direction conflict" in normalized:
            return "Direction conflict"

        if "probability" in normalized and "below research" in normalized:
            return "Research threshold"

        if "probability" in normalized and "below elite" in normalized:
            return "Elite threshold"

        if "open trade already exists" in normalized or "already exists" in normalized:
            return "Duplicate/open trade"

        if "cycle limit" in normalized:
            return "Cycle limit"

        if "spot_short_not_supported" in normalized:
            return "Spot short blocked"

        return "Other rejected"

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
            research_group=row["research_group"],
            experiment_tag=row["experiment_tag"],
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
            outcome_group=(
                row["outcome_group"]
                if "outcome_group" in row.keys()
                and row["outcome_group"]
                else TradeOutcomeGroup.NEUTRAL.value
            ),
            outcome_type=(
                row["outcome_type"]
                if "outcome_type" in row.keys()
                and row["outcome_type"]
                else TradeOutcomeType.OPEN_ACTIVE.value
            ),
            outcome_note=(
                row["outcome_note"]
                if "outcome_note" in row.keys()
                else None
            ),
            outcome_locked=(
                bool(row["outcome_locked"])
                if "outcome_locked" in row.keys()
                and row["outcome_locked"] is not None
                else False
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