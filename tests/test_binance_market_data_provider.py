from __future__ import annotations
import asyncio
from datetime import datetime,timedelta,timezone
from decimal import Decimal

from market_data.binance_provider import BinanceDailyProvider
from models.candle import Candle

class FakeBinance:
    def __init__(self):
        now=datetime.now(timezone.utc)
        self.closed=now-timedelta(hours=2)
        self.open_future=now+timedelta(hours=20)
    async def get_spot_symbols(self): return ["BTCUSDT","ETHUSDT","DOGEUSDT"]
    async def get_futures_symbols(self): return ["BTCUSDT","ETHUSDT"]
    async def get_ticker_24h(self):
        return [
            {"symbol":"BTCUSDT","quoteVolume":"1000000000","lastPrice":"60000"},
            {"symbol":"ETHUSDT","quoteVolume":"500000000","lastPrice":"3000"},
            {"symbol":"DOGEUSDT","quoteVolume":"100000000","lastPrice":"0.2"},
        ]
    async def get_futures_ticker_24h(self):
        return [
            {"symbol":"ETHUSDT","quoteVolume":"800000000","lastPrice":"3001"},
            {"symbol":"BTCUSDT","quoteVolume":"700000000","lastPrice":"60010"},
        ]
    async def get_klines(self,symbol,interval="1d",limit=365,futures=False):
        def candle(close_time,close):
            return Candle(
                open_time=close_time-timedelta(days=1),open=float(close)-1,high=float(close)+2,low=float(close)-3,
                close=float(close),volume=1000.0,close_time=close_time,quote_volume=1000000.0,trades=1,
                taker_buy_base_volume=500.0,taker_buy_quote_volume=500000.0,
            )
        return [candle(self.closed-timedelta(days=1),"100"),candle(self.closed,"101"),candle(self.open_future,"999")]

def test_spot_universe_ranked_by_provider_quote_volume():
    p=BinanceDailyProvider(futures=False,top_n=2,client=FakeBinance())
    u=asyncio.run(p.universe())
    assert [x.symbol for x in u]==["BTCUSDT","ETHUSDT"]
    assert all(x.asset_class=="CRYPTO_SPOT" for x in u)

def test_futures_universe_is_distinct_and_ranked():
    p=BinanceDailyProvider(futures=True,top_n=2,client=FakeBinance())
    u=asyncio.run(p.universe())
    assert [x.symbol for x in u]==["ETHUSDT","BTCUSDT"]
    assert all(x.asset_class=="CRYPTO_FUTURES" for x in u)

def test_current_unclosed_daily_bar_is_never_exposed():
    p=BinanceDailyProvider(futures=False,top_n=1,client=FakeBinance())
    instrument=asyncio.run(p.universe())[0]
    series=asyncio.run(p.history(instrument,limit=2))
    assert len(series.bars)==2
    assert all(bar.close != Decimal("999.0") for bar in series.bars)
    assert series.bars[-1].timestamp <= datetime.now(timezone.utc)

def test_liquidity_uses_provider_reported_quote_volume():
    p=BinanceDailyProvider(futures=False,top_n=1,client=FakeBinance())
    instrument=asyncio.run(p.universe())[0]
    liq=asyncio.run(p.liquidity(instrument))
    assert liq.average_daily_dollar_volume==Decimal("1000000000")
    assert liq.last_price==Decimal("60000")
