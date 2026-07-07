"""
MarketHunter

execution/binance_executor.py
"""

from __future__ import annotations

import ccxt.async_support as ccxt

from models.trade_order import TradeOrder
from models.trade_result import TradeResult

from execution.trade_executor import TradeExecutor


class BinanceExecutor(TradeExecutor):

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        sandbox: bool = True,
    ) -> None:

        self.exchange = ccxt.binance({

            "apiKey": api_key,

            "secret": api_secret,

            "enableRateLimit": True,

            "options": {

                "defaultType": "future",

            },

        })

        self.exchange.set_sandbox_mode(
            sandbox,
        )

    async def execute(
        self,
        order: TradeOrder,
    ) -> TradeResult:

        response = await self.exchange.create_market_order(

            symbol=order.symbol,

            side=order.side.lower(),

            amount=order.quantity,

        )

        return TradeResult(

            success=True,

            order_id=response["id"],

            symbol=order.symbol,

            side=order.side,

            quantity=order.quantity,

            price=float(response["average"] or order.entry),

            message="Executed",

        )

    async def close(self) -> None:

        await self.exchange.close()