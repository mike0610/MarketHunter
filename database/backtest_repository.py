"""
MarketHunter

database/backtest_repository.py
"""

from __future__ import annotations

from datetime import datetime

from database.repository import (
    Repository,
)

from models.backtest_result import (
    BacktestResult,
)


class BacktestRepository(
    Repository,
):

    def save(
        self,
        result: BacktestResult,
        strategy: str,
    ) -> None:

        cur = self.db.cursor()

        cur.execute(

            """

INSERT INTO backtests(

created,

strategy,

winrate,

profit_factor,

drawdown,

return_percent

)

VALUES(?,?,?,?,?,?)

""",

            (

                datetime.utcnow().isoformat(),

                strategy,

                result.win_rate,

                result.profit_factor,

                result.max_drawdown,

                result.total_return,

            ),

        )

        self.db.commit()