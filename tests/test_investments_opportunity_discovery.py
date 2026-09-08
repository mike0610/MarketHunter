import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from investments.opportunity_discovery import InvestmentOpportunityDiscovery
from investments.research_queue import InvestmentResearchQueue
from market_data.foundation import LiquidityEvidence, MarketInstrument


NOW = datetime(2026, 9, 8, 2, 0, tzinfo=timezone.utc)


class Provider:
    async def universe(self):
        return (
            MarketInstrument("AAA", "US_STOCK_OR_ETF", "USD"),
            MarketInstrument("BBB", "US_STOCK_OR_ETF", "USD"),
        )

    async def liquidity(self, instrument):
        adv = Decimal("20000000") if instrument.symbol == "AAA" else Decimal("1000")
        return LiquidityEvidence(
            instrument=instrument,
            average_daily_volume=Decimal("100000"),
            average_daily_dollar_volume=adv,
            last_price=Decimal("100"),
            provider="TEST",
            observed_at=NOW,
            source_reference=f"test:{instrument.symbol}",
        )

    async def history(self, *args, **kwargs):
        raise AssertionError("cheap screen must not require full history")


def test_discovery_admits_only_material_liquid_candidate(tmp_path):
    x = InvestmentOpportunityDiscovery(provider=Provider(), db_path=tmp_path / "r.db")
    summary = asyncio.run(x.run_once(NOW))
    assert summary.scanned == 2
    assert summary.admitted == 1
    assert [r["symbol"] for r in InvestmentResearchQueue(tmp_path / "r.db").pending()] == ["AAA"]


def test_discovery_runs_at_most_once_per_utc_day(tmp_path):
    x = InvestmentOpportunityDiscovery(provider=Provider(), db_path=tmp_path / "r.db")
    first = asyncio.run(x.run_once(NOW))
    second = asyncio.run(x.run_once(NOW))
    assert first.scanned == 2
    assert second.scanned == 0
    assert len(InvestmentResearchQueue(tmp_path / "r.db").pending()) == 1
