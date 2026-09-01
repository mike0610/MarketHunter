import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from experiment1.market_source import BinanceExperiment1QuoteSource
from experiment1.models import AccountKind, DecisionAction, OrderIntent


class FakeClient:
    def __init__(self, price="60000"):
        self.price = price
        self.calls = []

    async def get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {"symbol": "BTCUSDT", "price": self.price}


def _intent(account):
    action = DecisionAction.LONG if account is AccountKind.FUTURES else DecisionAction.BUY
    return OrderIntent(
        intent_id=f"quote-{account.value}",
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        account=account,
        action=action,
        symbol="BTCUSDT",
        quantity=Decimal("0.01"),
        reason="quote source test",
    )


def test_spot_quote_uses_public_spot_ticker():
    client = FakeClient()
    source = BinanceExperiment1QuoteSource(client)
    quote = asyncio.run(source.quote_for(_intent(AccountKind.SPOT)))

    assert quote.price == Decimal("60000")
    assert quote.source == "binance-public-rest"
    assert client.calls[0][0] == "/api/v3/ticker/price"
    assert "base_url" not in client.calls[0][1]


def test_futures_quote_uses_public_futures_ticker():
    client = FakeClient()
    source = BinanceExperiment1QuoteSource(client)
    quote = asyncio.run(source.quote_for(_intent(AccountKind.FUTURES)))

    assert quote.price == Decimal("60000")
    assert client.calls[0][0] == "/fapi/v1/ticker/price"
    assert client.calls[0][1]["base_url"].startswith("https://fapi.binance.com")


def test_invalid_price_returns_no_evidence():
    client = FakeClient("0")
    source = BinanceExperiment1QuoteSource(client)
    quote = asyncio.run(source.quote_for(_intent(AccountKind.SPOT)))

    assert quote is None
