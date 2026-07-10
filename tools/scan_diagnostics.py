"""
MarketHunter

Module:
Scan Diagnostics Helper

Responsibilities:
- Inspect local research SQLite database.
- Print scan-related tables.
- Print latest scan runs.
- Print latest signal rejection summaries when available.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


DATABASE_PATH = Path("data/research.db")


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


def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    rows = fetch_all(
        connection,
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    )

    return bool(rows)


def print_table_overview(
    connection: sqlite3.Connection,
) -> None:
    tables = fetch_all(
        connection,
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """,
    )

    print("")
    print("=== Tables ===")

    for table in tables:
        table_name = table["name"]

        count = connection.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]

        print(f"{table_name}: {count}")


def print_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> None:
    if not table_exists(
        connection,
        table_name,
    ):
        return

    columns = fetch_all(
        connection,
        f"PRAGMA table_info({table_name})",
    )

    print("")
    print(f"=== Columns: {table_name} ===")

    for column in columns:
        print(column["name"])


def print_latest_rows(
    connection: sqlite3.Connection,
    table_name: str,
    limit: int = 5,
) -> None:
    if not table_exists(
        connection,
        table_name,
    ):
        return

    columns = fetch_all(
        connection,
        f"PRAGMA table_info({table_name})",
    )

    column_names = [
        column["name"]
        for column in columns
    ]

    order_column = None

    for candidate in (
        "started_at",
        "created_at",
        "timestamp",
        "id",
    ):
        if candidate in column_names:
            order_column = candidate
            break

    if order_column is None:
        order_column = column_names[0]

    rows = fetch_all(
        connection,
        f"""
        SELECT *
        FROM {table_name}
        ORDER BY {order_column} DESC
        LIMIT ?
        """,
        (limit,),
    )

    print("")
    print(f"=== Latest rows: {table_name} ===")

    for row in rows:
        print(dict(row))


def print_signal_summaries(
    connection: sqlite3.Connection,
) -> None:
    candidate_tables = [
        "scan_signal_records",
        "scan_signals",
        "signal_records",
        "candidate_signals",
    ]

    table_name = None

    for candidate in candidate_tables:
        if table_exists(
            connection,
            candidate,
        ):
            table_name = candidate
            break

    if table_name is None:
        print("")
        print("=== Signal summaries ===")
        print("No known signal journal table found.")
        return

    columns = fetch_all(
        connection,
        f"PRAGMA table_info({table_name})",
    )

    column_names = [
        column["name"]
        for column in columns
    ]

    print("")
    print(f"=== Signal table: {table_name} ===")
    print("Columns:", ", ".join(column_names))

    for group_column in (
        "status",
        "result",
        "stage",
        "rejection_reason",
        "reject_reason",
        "strategy",
        "direction",
        "symbol",
    ):
        if group_column not in column_names:
            continue

        print("")
        print(f"--- Count by {group_column} ---")

        rows = fetch_all(
            connection,
            f"""
            SELECT {group_column}, COUNT(*) AS count
            FROM {table_name}
            GROUP BY {group_column}
            ORDER BY count DESC
            LIMIT 30
            """
        )

        for row in rows:
            print(dict(row))

    print_latest_rows(
        connection,
        table_name,
        limit=10,
    )


def print_recent_research_trades(
    connection: sqlite3.Connection,
) -> None:
    if not table_exists(
        connection,
        "research_trades",
    ):
        return

    print("")
    print("=== Recent research trades ===")

    rows = fetch_all(
        connection,
        """
        SELECT
            id,
            symbol,
            strategy,
            direction,
            probability,
            score,
            status,
            close_reason,
            created_at
        FROM research_trades
        ORDER BY created_at DESC
        LIMIT 15
        """,
    )

    for row in rows:
        print(dict(row))


def main() -> None:
    if not DATABASE_PATH.exists():
        print(f"Database not found: {DATABASE_PATH}")
        return

    connection = sqlite3.connect(
        DATABASE_PATH,
    )
    connection.row_factory = sqlite3.Row

    try:
        print_table_overview(
            connection,
        )

        for table_name in (
            "scan_runs",
            "scan_journal_runs",
            "scan_signal_records",
            "scan_signals",
            "signal_records",
            "candidate_signals",
            "research_trades",
        ):
            print_columns(
                connection,
                table_name,
            )
            print_latest_rows(
                connection,
                table_name,
                limit=5,
            )

        print_signal_summaries(
            connection,
        )

        print_recent_research_trades(
            connection,
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()