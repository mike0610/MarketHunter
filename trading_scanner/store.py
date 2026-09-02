"""
MarketHunter

trading_scanner/store.py

Module:
The persistent Trading Candidate Queue - a minimal, sqlite-backed
store, mirroring experiment1.engine.Experiment1Engine's own
connect-per-call/idempotent-insert pattern. A candidate is keyed by
its own deterministic dedupe_key (conid, setup_family, scan_cycle_id) -
never a randomly generated id - so re-running the same scan cycle
never duplicates a row. Rejected/blocked candidates are never deleted,
only ever inserted once and read back later for paper-outcome
statistics.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from trading_scanner.models import (
    CatalystEvidence,
    LiquidityContext,
    QueueState,
    SetupFamily,
    TradingCandidate,
    VolatilityContext,
)


class TradingScannerError(Exception):
    pass


class TradingScannerStore:
    """Persistent, restart-safe Trading Candidate Queue."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trading_scanner_candidates (
                    dedupe_key TEXT PRIMARY KEY,
                    conid INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    sec_type TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    setup_family TEXT NOT NULL,
                    reason_stack TEXT NOT NULL,
                    liquidity_avg_daily_volume TEXT NOT NULL,
                    liquidity_avg_daily_dollar_volume TEXT NOT NULL,
                    liquidity_last_price TEXT NOT NULL,
                    volatility_realized_range_pct TEXT NOT NULL,
                    evidence_status TEXT NOT NULL,
                    eligible INTEGER NOT NULL,
                    discovered_at TEXT NOT NULL,
                    scan_cycle_id TEXT NOT NULL,
                    queue_state TEXT NOT NULL,
                    catalyst_description TEXT,
                    catalyst_source TEXT,
                    catalyst_source_reference TEXT,
                    catalyst_observed_at TEXT,
                    freshness_note TEXT,
                    invalidation_reference TEXT,
                    reject_reason TEXT
                );
                """
            )

    def record_candidate(self, candidate: TradingCandidate) -> TradingCandidate:
        """
        Idempotent on dedupe_key: an identical resubmission (same
        content) returns the already-recorded row unchanged; a
        dedupe_key reused with different content raises - the same
        fail-closed collision contract Experiment1Engine already uses
        for intent_id/decision_id.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_scanner_candidates WHERE dedupe_key=?", (candidate.dedupe_key,)
            ).fetchone()
            if row is not None:
                existing = self._candidate_from_row(row)
                if existing == candidate:
                    return existing
                raise TradingScannerError("dedupe_key already exists with different content")

            conn.execute(
                """INSERT INTO trading_scanner_candidates (
                    dedupe_key, conid, symbol, sec_type, exchange, currency, setup_family,
                    reason_stack, liquidity_avg_daily_volume, liquidity_avg_daily_dollar_volume,
                    liquidity_last_price, volatility_realized_range_pct, evidence_status, eligible,
                    discovered_at, scan_cycle_id, queue_state, catalyst_description, catalyst_source,
                    catalyst_source_reference, catalyst_observed_at, freshness_note,
                    invalidation_reference, reject_reason
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    candidate.dedupe_key,
                    candidate.conid,
                    candidate.symbol,
                    candidate.sec_type,
                    candidate.exchange,
                    candidate.currency,
                    candidate.setup_family.value,
                    "\x1f".join(candidate.reason_stack),
                    str(candidate.liquidity.average_daily_volume),
                    str(candidate.liquidity.average_daily_dollar_volume),
                    str(candidate.liquidity.last_price),
                    str(candidate.volatility.realized_range_pct),
                    candidate.evidence_status,
                    1 if candidate.eligible else 0,
                    candidate.discovered_at.isoformat(),
                    candidate.scan_cycle_id,
                    candidate.queue_state.value,
                    None if candidate.catalyst is None else candidate.catalyst.description,
                    None if candidate.catalyst is None else candidate.catalyst.source,
                    None if candidate.catalyst is None else candidate.catalyst.source_reference,
                    None if candidate.catalyst is None else candidate.catalyst.observed_at.isoformat(),
                    candidate.freshness_note,
                    candidate.invalidation_reference,
                    candidate.reject_reason,
                ),
            )
            return candidate

    def get_candidate(self, dedupe_key: str) -> TradingCandidate | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trading_scanner_candidates WHERE dedupe_key=?", (dedupe_key,)
            ).fetchone()
            return None if row is None else self._candidate_from_row(row)

    def list_candidates(self, *, queue_state: QueueState | None = None) -> tuple[TradingCandidate, ...]:
        with self._connect() as conn:
            if queue_state is None:
                rows = conn.execute(
                    "SELECT * FROM trading_scanner_candidates ORDER BY discovered_at, dedupe_key"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trading_scanner_candidates WHERE queue_state=? ORDER BY discovered_at, dedupe_key",
                    (queue_state.value,),
                ).fetchall()
            return tuple(self._candidate_from_row(row) for row in rows)

    def _candidate_from_row(self, row: sqlite3.Row) -> TradingCandidate:
        catalyst = None
        if row["catalyst_description"] is not None:
            catalyst = CatalystEvidence(
                description=row["catalyst_description"],
                source=row["catalyst_source"],
                source_reference=row["catalyst_source_reference"],
                observed_at=datetime.fromisoformat(row["catalyst_observed_at"]),
            )
        return TradingCandidate(
            conid=row["conid"],
            symbol=row["symbol"],
            sec_type=row["sec_type"],
            exchange=row["exchange"],
            currency=row["currency"],
            setup_family=SetupFamily(row["setup_family"]),
            reason_stack=tuple(row["reason_stack"].split("\x1f")),
            liquidity=LiquidityContext(
                average_daily_volume=Decimal(row["liquidity_avg_daily_volume"]),
                average_daily_dollar_volume=Decimal(row["liquidity_avg_daily_dollar_volume"]),
                last_price=Decimal(row["liquidity_last_price"]),
            ),
            volatility=VolatilityContext(realized_range_pct=Decimal(row["volatility_realized_range_pct"])),
            evidence_status=row["evidence_status"],
            eligible=bool(row["eligible"]),
            discovered_at=datetime.fromisoformat(row["discovered_at"]),
            scan_cycle_id=row["scan_cycle_id"],
            dedupe_key=row["dedupe_key"],
            queue_state=QueueState(row["queue_state"]),
            catalyst=catalyst,
            freshness_note=row["freshness_note"],
            invalidation_reference=row["invalidation_reference"],
            reject_reason=row["reject_reason"],
        )
