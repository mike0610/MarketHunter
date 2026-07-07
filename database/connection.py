"""
MarketHunter

database/connection.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class DatabaseConnection:

    def __init__(
        self,
        path: str = "markethunter.db",
    ) -> None:

        Path(path).touch(
            exist_ok=True,
        )

        self.connection = sqlite3.connect(
            path,
        )

        self.connection.row_factory = (
            sqlite3.Row
        )

    def cursor(
        self,
    ):

        return self.connection.cursor()

    def commit(
        self,
    ) -> None:

        self.connection.commit()

    def close(
        self,
    ) -> None:

        self.connection.close()