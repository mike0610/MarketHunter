from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.momentum_acceleration import MomentumAccelerationStrategy
def c(i,o,h,l,cl,vol=1000):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,vol,t+timedelta(hours=1),100000,100,vol*.5,vol*50)
def snap(cs,e20=105,e50=100,e200=95):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))
class MomentumAccelerationTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_acceleration(self):
  hist=[c(i,100,101,99,100) for i in range(26)]
  w=[c(26,100,101,99.8,100.2),c(27,100.2,101,100,100.5),c(28,100.5,101.3,100.3,101),c(29,101,103,100.8,102.2,1400)]
  s=await MomentumAccelerationStrategy().analyze(snap(hist+w));self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_acceleration(self):
  hist=[c(i,100,101,99,100) for i in range(26)]
  w=[c(26,100,100.2,99,99.8),c(27,99.8,100,99,99.5),c(28,99.5,99.7,98.5,99),c(29,99,99.2,97,97.8,1400)]
  s=await MomentumAccelerationStrategy().analyze(snap(hist+w,95,100,105));self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_without_volume_expansion(self):
  hist=[c(i,100,101,99,100) for i in range(26)]
  w=[c(26,100,101,99.8,100.2),c(27,100.2,101,100,100.5),c(28,100.5,101.3,100.3,101),c(29,101,103,100.8,102.2,1000)]
  self.assertIsNone(await MomentumAccelerationStrategy().analyze(snap(hist+w)))
 async def test_rejects_without_full_trend_alignment(self):
  hist=[c(i,100,101,99,100) for i in range(26)]
  w=[c(26,100,101,99.8,100.2),c(27,100.2,101,100,100.5),c(28,100.5,101.3,100.3,101),c(29,101,103,100.8,102.2,1400)]
  self.assertIsNone(await MomentumAccelerationStrategy().analyze(snap(hist+w,105,100,101)))
if __name__=="__main__":unittest.main()
