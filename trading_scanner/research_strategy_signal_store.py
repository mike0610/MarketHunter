"""Persistent observation store for unchanged Research-strategy signals."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from trading_scanner.research_strategy_pipe import PipedSignal


@dataclass(frozen=True, slots=True)
class StoredPipedSignal:
    symbol: str
    strategy: str
    direction: str
    score: float
    reasons: tuple[str, ...]
    observed_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    observations: int


class ResearchStrategySignalStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init(self):
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS research_strategy_signals (
                    symbol TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    score REAL NOT NULL,
                    reasons TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    observations INTEGER NOT NULL,
                    PRIMARY KEY(symbol, strategy, direction, observed_at)
                )
                """
            )

    def record_many(self, signals: tuple[PipedSignal, ...], *, seen_at: datetime) -> int:
        with self._connect() as con:
            for signal in signals:
                key = (
                    signal.symbol,
                    signal.strategy,
                    signal.direction,
                    signal.observed_at.isoformat(),
                )
                row = con.execute(
                    """SELECT observations FROM research_strategy_signals
                       WHERE symbol=? AND strategy=? AND direction=? AND observed_at=?""",
                    key,
                ).fetchone()
                if row is None:
                    con.execute(
                        """INSERT INTO research_strategy_signals
                           (symbol,strategy,direction,score,reasons,observed_at,
                            first_seen_at,last_seen_at,observations)
                           VALUES (?,?,?,?,?,?,?,?,1)""",
                        (
                            *key[:3],
                            signal.score,
                            "\n".join(signal.reasons),
                            key[3],
                            seen_at.isoformat(),
                            seen_at.isoformat(),
                        ),
                    )
                else:
                    con.execute(
                        """UPDATE research_strategy_signals
                           SET score=?, reasons=?, last_seen_at=?, observations=?
                           WHERE symbol=? AND strategy=? AND direction=? AND observed_at=?""",
                        (
                            signal.score,
                            "\n".join(signal.reasons),
                            seen_at.isoformat(),
                            int(row["observations"]) + 1,
                            *key,
                        ),
                    )
        return len(signals)

    def list(self, *, limit: int = 500) -> tuple[StoredPipedSignal, ...]:
        with self._connect() as con:
            rows = con.execute(
                """SELECT * FROM research_strategy_signals
                   ORDER BY observed_at DESC, strategy, symbol LIMIT ?""",
                (limit,),
            ).fetchall()
        return tuple(
            StoredPipedSignal(
                symbol=row["symbol"],
                strategy=row["strategy"],
                direction=row["direction"],
                score=float(row["score"]),
                reasons=tuple(x for x in row["reasons"].split("\n") if x),
                observed_at=datetime.fromisoformat(row["observed_at"]),
                first_seen_at=datetime.fromisoformat(row["first_seen_at"]),
                last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
                observations=int(row["observations"]),
            )
            for row in rows
        )
