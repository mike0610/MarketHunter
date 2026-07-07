"""
MarketHunter

database/repository.py
"""

from __future__ import annotations

from database.connection import (
    DatabaseConnection,
)


class Repository:

    def __init__(
        self,
        db: DatabaseConnection,
    ) -> None:

        self.db = db