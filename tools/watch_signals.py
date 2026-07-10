"""
MarketHunter

Module:
Local Signal Watcher

Responsibilities:
- Watch local research SQLite database.
- Detect new research trades after watcher start.
- Detect new elite signal records after watcher start.
- Print alert details and play a Windows beep.
- Does not modify the database.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any


DATABASE_PATH = Path("data/research.db")
POLL_SECONDS = 60


def beep() -> None:
    try:
        import winsound

        for _ in range(3):
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            time.sleep(0.4)
    except Exception:
        print("\a\a\a")


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(
        DATABASE_PATH,
    )
    connection.row_factory = sqlite3.Row

    return connection


def fetch_all(
    connection: sqlite3.Connection,
    query: str,
    params: tuple[Any, ...] = (),
) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            query,
            params,
        )
    )


def fetch_trade_ids(
    connection: sqlite3.Connection,
) -> set[str]:
    rows = fetch_all(
        connection,
        """
        SELECT id
        FROM research_trades
        """,
    )

    return {
        str(row["id"])
        for row in rows
    }


def fetch_elite_signal_ids(
    connection: sqlite3.Connection,
) -> set[str]:
    rows = fetch_all(
        connection,
        """
        SELECT id
        FROM signal_records
        WHERE status = 'elite'
        OR is_elite = 1
        """,
    )

    return {
        str(row["id"])
        for row in rows
    }


def fetch_latest_scan(
    connection: sqlite3.Connection,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT
            id,
            started_at,
            finished_at,
            status,
            symbols_scanned,
            candidate_signals,
            research_trades_created,
            elite_signals_found,
            error
        FROM scan_runs
        ORDER BY started_at DESC
        LIMIT 1
        """
    ).fetchone()


def fetch_new_trades(
    connection: sqlite3.Connection,
    known_trade_ids: set[str],
) -> list[sqlite3.Row]:
    if not known_trade_ids:
        return fetch_all(
            connection,
            """
            SELECT
                id,
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
                status,
                close_reason,
                created_at
            FROM research_trades
            ORDER BY created_at DESC
            """
        )

    placeholders = ",".join(
        "?"
        for _ in known_trade_ids
    )

    return fetch_all(
        connection,
        f"""
        SELECT
            id,
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
            status,
            close_reason,
            created_at
        FROM research_trades
        WHERE id NOT IN ({placeholders})
        ORDER BY created_at DESC
        """,
        tuple(known_trade_ids),
    )


def fetch_new_elite_signals(
    connection: sqlite3.Connection,
    known_elite_ids: set[str],
) -> list[sqlite3.Row]:
    if not known_elite_ids:
        return fetch_all(
            connection,
            """
            SELECT
                id,
                symbol,
                market,
                timeframe,
                strategy,
                direction,
                probability,
                score,
                status,
                rejected_reason,
                created_at
            FROM signal_records
            WHERE status = 'elite'
            OR is_elite = 1
            ORDER BY created_at DESC
            """
        )

    placeholders = ",".join(
        "?"
        for _ in known_elite_ids
    )

    return fetch_all(
        connection,
        f"""
        SELECT
            id,
            symbol,
            market,
            timeframe,
            strategy,
            direction,
            probability,
            score,
            status,
            rejected_reason,
            created_at
        FROM signal_records
        WHERE (
            status = 'elite'
            OR is_elite = 1
        )
        AND id NOT IN ({placeholders})
        ORDER BY created_at DESC
        """,
        tuple(known_elite_ids),
    )


def print_trade_alert(
    trade: sqlite3.Row,
) -> None:
    print("")
    print("=" * 80)
    print("NEW RESEARCH TRADE FOUND")
    print("=" * 80)
    print(f"ID:          {trade['id']}")
    print(f"Symbol:      {trade['symbol']}")
    print(f"Market:      {trade['market']}")
    print(f"Timeframe:   {trade['timeframe']}")
    print(f"Strategy:    {trade['strategy']}")
    print(f"Direction:   {trade['direction']}")
    print(f"Probability: {trade['probability']}%")
    print(f"Score:       {trade['score']}")
    print(f"Entry:       {trade['entry_price']}")
    print(f"SL:          {trade['stop_loss']}")
    print(f"TP:          {trade['take_profit']}")
    print(f"Status:      {trade['status']}")
    print(f"Reason:      {trade['close_reason']}")
    print(f"Created:     {trade['created_at']}")
    print("=" * 80)
    print("Copy this block to ChatGPT for analysis.")
    print("=" * 80)
    print("")


def print_elite_alert(
    signal: sqlite3.Row,
) -> None:
    print("")
    print("=" * 80)
    print("NEW ELITE SIGNAL FOUND")
    print("=" * 80)
    print(f"ID:          {signal['id']}")
    print(f"Symbol:      {signal['symbol']}")
    print(f"Market:      {signal['market']}")
    print(f"Timeframe:   {signal['timeframe']}")
    print(f"Strategy:    {signal['strategy']}")
    print(f"Direction:   {signal['direction']}")
    print(f"Probability: {signal['probability']}%")
    print(f"Score:       {signal['score']}")
    print(f"Status:      {signal['status']}")
    print(f"Reason:      {signal['rejected_reason']}")
    print(f"Created:     {signal['created_at']}")
    print("=" * 80)
    print("Copy this block to ChatGPT for analysis.")
    print("=" * 80)
    print("")


def print_scan_status(
    scan: sqlite3.Row | None,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if scan is None:
        print(f"[{now}] No scan runs found yet.")
        return

    print(
        f"[{now}] Latest scan {scan['status']} | "
        f"signals={scan['candidate_signals']} | "
        f"research={scan['research_trades_created']} | "
        f"elite={scan['elite_signals_found']} | "
        f"finished={scan['finished_at']}"
    )


def main() -> None:
    if not DATABASE_PATH.exists():
        print(f"Database not found: {DATABASE_PATH}")
        return

    with connect() as connection:
        known_trade_ids = fetch_trade_ids(
            connection,
        )
        known_elite_ids = fetch_elite_signal_ids(
            connection,
        )

    print("")
    print("MarketHunter watcher started.")
    print(f"Database: {DATABASE_PATH}")
    print(f"Known research trades at start: {len(known_trade_ids)}")
    print(f"Known elite signals at start: {len(known_elite_ids)}")
    print(f"Polling every {POLL_SECONDS} seconds.")
    print("")
    print("Leave this window open. It will beep when something new appears.")
    print("Press Ctrl+C to stop.")
    print("")

    while True:
        try:
            with connect() as connection:
                latest_scan = fetch_latest_scan(
                    connection,
                )

                print_scan_status(
                    latest_scan,
                )

                new_trades = fetch_new_trades(
                    connection,
                    known_trade_ids,
                )

                new_elite_signals = fetch_new_elite_signals(
                    connection,
                    known_elite_ids,
                )

                if new_trades or new_elite_signals:
                    beep()

                for trade in new_trades:
                    known_trade_ids.add(
                        str(trade["id"])
                    )
                    print_trade_alert(
                        trade,
                    )

                for signal in new_elite_signals:
                    known_elite_ids.add(
                        str(signal["id"])
                    )
                    print_elite_alert(
                        signal,
                    )

            time.sleep(
                POLL_SECONDS,
            )

        except KeyboardInterrupt:
            print("")
            print("Watcher stopped.")
            return

        except Exception as exc:
            print("")
            print(f"Watcher error: {type(exc).__name__}: {exc}")
            print("Retrying...")
            time.sleep(
                POLL_SECONDS,
            )


if __name__ == "__main__":
    main()