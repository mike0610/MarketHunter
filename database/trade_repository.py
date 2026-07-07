"""
MarketHunter

database/trade_repository.py
"""

from __future__ import annotations

from datetime import datetime

from database.repository import (
    Repository,
)


class TradeRepository(
    Repository,
):

    def save(

        self,

        symbol: str,

        side: str,

        entry: float,

        exit_price: float,

        pnl: float,

    ) -> None:

        cur = self.db.cursor()

        cur.execute(

            """

INSERT INTO trades(

opened,

closed,

symbol,

side,

entry,

exit,

pnl

)

VALUES(?,?,?,?,?,?,?)

""",

            (

                datetime.utcnow().isoformat(),

                datetime.utcnow().isoformat(),

                symbol,

                side,

                entry,

                exit_price,

                pnl,

            ),

        )

        self.db.commit()