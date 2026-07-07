"""
MarketHunter

database/database.py
"""

from __future__ import annotations

from database.connection import (
    DatabaseConnection,
)

from database.schema import (
    Schema,
)


class Database:

    def __init__(self) -> None:

        self.connection = DatabaseConnection()

        Schema().create(
            self.connection,
        )

    def close(
        self,
    ) -> None:

        self.connection.close()