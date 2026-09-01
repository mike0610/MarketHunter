from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from exchange.binance_client import BinanceClient
from exchange.endpoints import FUTURES_BASE_URL
from experiment1.models import AccountKind, MarketQuote, OrderIntent


class BinanceExperiment1QuoteSource:
    """Read-only Binance quote source for Experiment 1 paper execution.

    It supplies reference prices only. Fee and slippage assumptions remain
    explicit caller policy and default to zero only when configured as zero.
    No live orders are ever submitted here.
    """

    def __init__(
        self,
        client: BinanceClient | None = None,
        *,
        fee_bps: Decimal = Decimal("0"),
        slippage_bps: Decimal = Decimal("0"),
    ) -> None:
        if fee_bps < 0 or slippage_bps < 0:
            raise ValueError("fee_bps/slippage_bps must be non-negative")
        self.client = client or BinanceClient()
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    async def quote_for(self, intent: OrderIntent) -> MarketQuote | None:
        symbol = intent.symbol.upper()
        if intent.account is AccountKind.FUTURES:
            payload = await self.client.get(
                "/fapi/v1/ticker/price",
                base_url=FUTURES_BASE_URL,
                params={"symbol": symbol},
            )
            market = "futures"
        else:
            payload = await self.client.get(
                "/api/v3/ticker/price",
                params={"symbol": symbol},
            )
            market = "spot"

        if not isinstance(payload, dict):
            return None
        price_raw = payload.get("price")
        if price_raw in (None, ""):
            return None
        price = Decimal(str(price_raw))
        if price <= 0:
            return None

        observed_at = datetime.now(timezone.utc)
        return MarketQuote(
            symbol=symbol,
            price=price,
            observed_at=observed_at,
            source="binance-public-rest",
            source_reference=f"{market}:ticker-price:{symbol}:{observed_at.isoformat()}",
            fee_bps=self.fee_bps,
            slippage_bps=self.slippage_bps,
        )
