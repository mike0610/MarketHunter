from datetime import datetime, timezone
from decimal import Decimal

from market_data.foundation import LiquidityEvidence, MarketBar, MarketInstrument, MarketSeries
from models.signal import Signal
from trading_scanner import research_strategy_pipe as pipe
from trading_scanner.models import QueueState, SetupFamily
from trading_scanner.store import TradingScannerStore


NOW = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self):
        self.instrument = MarketInstrument("ABC", "US_STOCK_OR_ETF", "USD")

    async def universe(self):
        return (self.instrument,)

    async def liquidity(self, instrument):
        return LiquidityEvidence(
            instrument=instrument,
            average_daily_volume=Decimal("1000000"),
            average_daily_dollar_volume=Decimal("100000000"),
            last_price=Decimal("100"),
            provider="FAKE",
            observed_at=NOW,
            source_reference="fake",
        )

    async def history(self, instrument, *, timeframe="1d", limit=500):
        bars = tuple(
            MarketBar(
                timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=Decimal("1000000"),
            )
            for _ in range(200)
        )
        return MarketSeries(
            instrument=instrument,
            timeframe="1d",
            bars=bars,
            provider="FAKE",
            source_reference="fake",
            observed_at=NOW,
            available_at=NOW,
        )


class FakeStrategy:
    async def analyze(self, snapshot):
        return Signal(
            symbol=snapshot.symbol,
            strategy="Compression",
            direction="LONG",
            score=87.0,
            reasons=["existing strategy signal"],
        )


def test_pipe_records_existing_strategy_signal_without_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pipe,
        "STRATEGY_PIPE",
        ((SetupFamily.COMPRESSION, FakeStrategy),),
    )
    store = TradingScannerStore(tmp_path / "scanner.db")

    import asyncio
    rows = asyncio.run(
        pipe.run_research_strategy_pipe(
            FakeProvider(),
            store,
            scan_cycle_id="cycle-1",
            now=NOW,
        )
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.setup_family is SetupFamily.COMPRESSION
    assert row.queue_state is QueueState.CANDIDATE
    assert row.signal_direction == "LONG"
    assert row.signal_score == Decimal("87.0")
    assert row.reason_stack == ("existing strategy signal",)

    persisted = store.get_candidate(row.dedupe_key)
    assert persisted == row


def test_pipe_contains_only_requested_positive_strategy_classes():
    assert tuple(family for family, _ in pipe.STRATEGY_PIPE) == (
        SetupFamily.PREMIUM_DISCOUNT,
        SetupFamily.BREAKOUT,
        SetupFamily.ORDER_BLOCK,
        SetupFamily.COMPRESSION,
        SetupFamily.LIQUIDITY_SWEEP,
    )
