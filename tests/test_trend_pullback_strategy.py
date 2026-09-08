from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.trend_pullback import TrendPullbackStrategy

def candle(i,o,h,l,c):
    t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=4*i)
    return Candle(t,o,h,l,c,1000.0,t+timedelta(hours=4)-timedelta(seconds=1),100000.0,100,500.0,50000.0)

def snapshot(candles,ema20,ema50,ema200,atr=2.0):
    return MarketSnapshot("BTCUSDT",candles,ema20,ema50,ema200,atr,1000.0,max(x.high for x in candles[-20:]),min(x.low for x in candles[-20:]))

class TrendPullbackStrategyTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_requires_aligned_trend_and_reclaim(self):
        candles=[candle(i,100,103,99,102) for i in range(48)]
        candles += [candle(48,106,107,101,102),candle(49,102,106,99,105)]
        s=await TrendPullbackStrategy().analyze(snapshot(candles,103,100,95))
        self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG");self.assertEqual(s.strategy,"TrendPullback")
        self.assertEqual(s.metadata["trend_alignment"],"with_trend");self.assertGreater(s.metadata["take_profit"],s.metadata["entry"])

    async def test_short_requires_aligned_trend_and_reclaim(self):
        candles=[candle(i,100,101,97,98) for i in range(48)]
        candles += [candle(48,94,100,93,98),candle(49,98,101,94,95)]
        s=await TrendPullbackStrategy().analyze(snapshot(candles,97,100,105))
        self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT");self.assertLess(s.metadata["take_profit"],s.metadata["entry"])

    async def test_rejects_without_full_trend_alignment(self):
        candles=[candle(i,100,103,99,102) for i in range(48)]
        candles += [candle(48,106,107,101,102),candle(49,102,106,99,105)]
        s=await TrendPullbackStrategy().analyze(snapshot(candles,103,100,101))
        self.assertIsNone(s)

    async def test_rejects_without_pullback_touch(self):
        candles=[candle(i,110,112,108,111) for i in range(50)]
        s=await TrendPullbackStrategy().analyze(snapshot(candles,103,100,95))
        self.assertIsNone(s)

if __name__=="__main__":unittest.main()
