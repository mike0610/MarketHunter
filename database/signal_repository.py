"""
MarketHunter

database/signal_repository.py
"""

from __future__ import annotations

from datetime import datetime

from database.repository import (
    Repository,
)

from models.signal import Signal


class SignalRepository(
    Repository,
):

    def save(
        self,
        signal: Signal,
    ) -> None:

        cur = self.db.cursor()

        cur.execute(

            """

INSERT INTO signals(

created,

symbol,

market,

strategy,

direction,

score

)

VALUES(?,?,?,?,?,?)

""",

            (

                datetime.utcnow().isoformat(),

                signal.symbol,

                signal.market,

                signal.strategy,

                signal.direction,

                signal.score,

            ),

        )

        self.db.commit()