"""Forward-only read-only Research signal intake for a separate experimental book.

This file NEVER opens an order or imports the canonical Experiment1 paper engine.
Signals observed before the one-time arm epoch stay historical forever.
"""
from __future__ import annotations

from contextlib import contextmanager, closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3

UTC = timezone.utc
MAX_AGE = timedelta(days=4)
VALID_DIRECTIONS = frozenset({"LONG", "SHORT"})
VALID_STRATEGIES = frozenset({"PremiumDiscount", "Breakout", "OrderBlock", "Compression", "LiquiditySweep"})


@dataclass(frozen=True)
class IntakeSummary:
    source_rows: int
    previously_seen: int
    historical_ignored: int
    invalid_ignored: int
    new_waiting_evidence: int
    armed_at: str


def _parse_utc(raw: str) -> datetime:
    value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _source_ro(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"Signal store not found: {path}")
    con = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    columns = {r[1] for r in con.execute("PRAGMA table_info(research_strategy_signals)")}
    required = {"symbol", "strategy", "direction", "observed_at", "first_seen_at"}
    if not required.issubset(columns):
        con.close()
        raise ValueError("Research signal source schema lacks forward timing fields")
    return con


class ForwardSignalGate:
    """Reads source SQLite mode=ro; writes only a distinct sandbox SQLite file."""

    def __init__(self, source_db: str | Path, sandbox_db: str | Path) -> None:
        self.source_db = Path(source_db)
        self.sandbox_db = Path(sandbox_db)
        if self.source_db.resolve() == self.sandbox_db.resolve():
            raise ValueError("sandbox_db must differ from source_db")

    def _sandbox(self) -> sqlite3.Connection:
        self.sandbox_db.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.sandbox_db)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("CREATE TABLE IF NOT EXISTS gate_meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("""CREATE TABLE IF NOT EXISTS paper_signal_intake (
            signal_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, strategy TEXT NOT NULL,
            direction TEXT NOT NULL, signal_observed_at TEXT NOT NULL,
            first_seen_at TEXT NOT NULL, admitted_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('WAITING_EVIDENCE', 'OPENED', 'BLOCKED', 'EXPIRED')),
            reason TEXT NOT NULL
        )""")
        return con

    @contextmanager
    def _write_db(self):
        con = self._sandbox()
        try:
            with con:
                yield con
        finally:
            con.close()

    def arm(self, *, now: datetime | None = None) -> str:
        """Save epoch once; never re-arm to make historical signals fresh."""
        moment = (now or datetime.now(UTC)).astimezone(UTC)
        with self._write_db() as db:
            prior = db.execute("SELECT value FROM gate_meta WHERE name='armed_at'").fetchone()
            if prior:
                return prior[0]
            db.execute("INSERT INTO gate_meta(name,value) VALUES('armed_at',?)", (moment.isoformat(),))
        return moment.isoformat()

    def collect(self, *, now: datetime | None = None) -> IntakeSummary:
        clock = (now or datetime.now(UTC)).astimezone(UTC)
        with closing(_source_ro(self.source_db)) as src, self._write_db() as dst:
            prior = dst.execute("SELECT value FROM gate_meta WHERE name='armed_at'").fetchone()
            if not prior:
                raise ValueError("sandbox not armed; call arm() before collecting")
            armed = _parse_utc(prior[0])
            rows = src.execute("""SELECT symbol,strategy,direction,observed_at,first_seen_at
                FROM research_strategy_signals ORDER BY first_seen_at,symbol,strategy""").fetchall()
            historical = invalid = existing = admitted = 0
            for row in rows:
                try:
                    observed = _parse_utc(row["observed_at"])
                    first_seen = _parse_utc(row["first_seen_at"])
                except (ValueError, TypeError, OverflowError):
                    invalid += 1
                    continue
                if first_seen <= armed:
                    historical += 1
                    continue
                symbol = str(row["symbol"]).strip().upper()
                strategy = str(row["strategy"])
                direction = str(row["direction"]).strip().upper()
                if (
                    not symbol or strategy not in VALID_STRATEGIES
                    or direction not in VALID_DIRECTIONS
                    or observed > clock or first_seen > clock
                    or first_seen < observed or clock - observed > MAX_AGE
                ):
                    invalid += 1
                    continue
                key = "\x1f".join((symbol, strategy, direction, observed.isoformat()))
                signal_id = sha256(key.encode("utf-8")).hexdigest()
                if dst.execute("SELECT 1 FROM paper_signal_intake WHERE signal_id=?", (signal_id,)).fetchone():
                    existing += 1
                    continue
                dst.execute("""INSERT INTO paper_signal_intake
                  (signal_id,symbol,strategy,direction,signal_observed_at,
                   first_seen_at,admitted_at,status,reason)
                  VALUES(?,?,?,?,?,?,?,'WAITING_EVIDENCE','new forward signal; quote and rules pending')""",
                  (signal_id,symbol,strategy,direction,observed.isoformat(),
                   first_seen.isoformat(),clock.isoformat()))
                admitted += 1
            return IntakeSummary(len(rows),existing,historical,invalid,admitted,armed.isoformat())

    def snapshot(self) -> dict:
        with self._write_db() as db:
            armed = db.execute("SELECT value FROM gate_meta WHERE name='armed_at'").fetchone()
            states = db.execute("SELECT status,COUNT(*) FROM paper_signal_intake GROUP BY status").fetchall()
            return {
                "armed_at": armed[0] if armed else None,
                "by_status": {r[0]: r[1] for r in states},
                "note": "WAITING_EVIDENCE is not a fill or position."
            }
