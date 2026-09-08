from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.statistical_mean_reversion import StatisticalMeanReversionStrategy
def c(i,o,h,l,cl):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,1000,t+timedelta(hours=1),100000,100,500,50000)
def snap(cs,e20=100,e50=100,e200=100,atr=2):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,atr,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))
class StatisticalMeanReversionTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_extreme_then_reversal_confirmation(self):
  hist=[c(i,99.5,101,99,100+(i%3-1)*.5) for i in range(33)]
  prior=c(33,100,98,94,95); trigger=c(34,95,100,94.5,99)
  s=await StatisticalMeanReversionStrategy().analyze(snap(hist+[prior,trigger]))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG");self.assertLessEqual(s.metadata["zscore"],-2)
 async def test_short_extreme_then_reversal_confirmation(self):
  hist=[c(i,99.5,101,99,100+(i%3-1)*.5) for i in range(33)]
  prior=c(33,100,106,102,105); trigger=c(34,105,105.5,100,101)
  s=await StatisticalMeanReversionStrategy().analyze(snap(hist+[prior,trigger]))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT");self.assertGreaterEqual(s.metadata["zscore"],2)
 async def test_rejects_extreme_without_confirmation(self):
  hist=[c(i,99.5,101,99,100+(i%3-1)*.5) for i in range(33)]
  prior=c(33,100,98,94,95); trigger=c(34,95,97,93,94)
  self.assertIsNone(await StatisticalMeanReversionStrategy().analyze(snap(hist+[prior,trigger])))
 async def test_rejects_strong_ema_regime(self):
  hist=[c(i,99.5,101,99,100+(i%3-1)*.5) for i in range(33)]
  prior=c(33,100,98,94,95); trigger=c(34,95,100,94.5,99)
  self.assertIsNone(await StatisticalMeanReversionStrategy().analyze(snap(hist+[prior,trigger],110,100,95,2)))
if __name__=="__main__":unittest.main()
