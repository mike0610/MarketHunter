"""One-time, explicitly invoked reconciliation for PRE-FIX expired WEEX spot signals.

Not part of the live agent loop. Never calls Telegram, exchanges or brokers.
All records are preserved; old unresolved signals are labeled UNVERIFIED,
not incorrectly counted as confirmations, expirations or losses.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

MIGRATION_KEY = "lifecycle_prefetch_fix_20260930_legacy_reconciled"
ONE_DAY_MS = 24 * 60 * 60 * 1000


def retire_legacy_overdue(
    conn: sqlite3.Connection, *, as_of_ms: int, minimum_overdue_ms: int = ONE_DAY_MS
) -> dict:
    if minimum_overdue_ms < 0:
        raise ValueError("minimum_overdue_ms must be nonnegative")
    conn.execute("CREATE TABLE IF NOT EXISTS agent_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    existing = conn.execute("SELECT value FROM agent_meta WHERE key=?", (MIGRATION_KEY,)).fetchone()
    if existing:
        return {"already_applied": True, "retired": 0, "marker": existing[0]}
    cutoff_ms = as_of_ms - minimum_overdue_ms
    rows = conn.execute(
        """SELECT symbol,signal_candle_ms,expires_ms,direction,range_high,range_low
           FROM active_breakouts WHERE status='ACTIVE' AND expires_ms <= ?
           ORDER BY expires_ms,symbol""",
        (cutoff_ms,),
    ).fetchall()
    stamp = datetime.fromtimestamp(as_of_ms / 1000, timezone.utc).isoformat()
    retired = 0
    for symbol, signal_ms, expiry_ms, direction, high, low in rows:
        # Do not replay old candles or retroactively fabricate an outcome.
        # Historical candidates remain in 'events' for future cohort audits.
        recorded = conn.execute(
            """SELECT 1 FROM lifecycle_events WHERE symbol=? AND signal_candle_ms=?
               AND state IN ('BREAKOUT_INVALIDATED','BREAKOUT_EXPIRED','BREAKOUT_UNVERIFIED') LIMIT 1""",
            (symbol, signal_ms),
        ).fetchone()
        if recorded:
            # Preserve inconsistencies for manual review, rather than rewriting
            # a previously settled outcome or inserting a contradictory one.
            continue
        payload = {
            "symbol": symbol,
            "state": "BREAKOUT_UNVERIFIED",
            "direction": direction or "LONG",
            "signal_candle_ms": signal_ms,
            "candle_close_ms": expiry_ms,
            "observed_at_utc": stamp,
            "mode": "PAPER_ONLY_NO_ORDERS",
            "historical_reconciliation": True,
            "reason": "PRE_FIX_STALE_NO_TRUSTWORTHY_HISTORICAL_REPLAY",
        }
        conn.execute(
            """INSERT OR IGNORE INTO lifecycle_events
               (symbol,signal_candle_ms,state,candle_close_ms,observed_at_utc,payload_json)
               VALUES(?,?,?,?,?,?)""",
            (symbol, signal_ms, payload["state"], expiry_ms, stamp,
             json.dumps(payload, ensure_ascii=False)),
        )
        conn.execute(
            """UPDATE active_breakouts SET status='BREAKOUT_UNVERIFIED',
               resolved_candle_ms=expires_ms,resolved_close=NULL
               WHERE symbol=? AND signal_candle_ms=? AND status='ACTIVE'""",
            (symbol, signal_ms),
        )
        retired += 1

    marker = json.dumps({
        "applied_at": stamp, "minimum_overdue_hours": minimum_overdue_ms / 3_600_000,
        "retired": retired, "skipped_conflicting": len(rows)-retired,
        "telegram_queued": False,
    }, sort_keys=True)
    conn.execute("INSERT INTO agent_meta(key,value) VALUES(?,?)", (MIGRATION_KEY, marker))
    return {
        "already_applied": False,
        "cutoff_ms": cutoff_ms,
        "retired": retired,
        "skipped_conflicting": len(rows)-retired,
        "telegram_queued": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--apply", action="store_true", help="Explicitly apply after stopping the agent and backing up DB")
    args = parser.parse_args()
    path = Path(args.db)
    if not path.is_file():
        parser.error("WEEX agent DB is missing")
    if args.apply:
        with sqlite3.connect(path, timeout=30) as conn:
            with conn:
                result = retire_legacy_overdue(conn, as_of_ms=int(time.time() * 1000))
    else:
        with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as conn:
            cutoff = int(time.time()*1000)-ONE_DAY_MS
            count = conn.execute(
                "SELECT count(*) FROM active_breakouts WHERE status='ACTIVE' AND expires_ms <= ?",
                (cutoff,),
            ).fetchone()[0]
            result = {"dry_run": True, "old_overdue_candidates": count, "telegram_queued": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
