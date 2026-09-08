from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.breakout_retest import BreakoutRetestStrategy
def c(i,o,h,l,cl):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,1000,t+timedelta(hours=1),100000,100,500,50000)
def snap(cs,e20=105,e50=100,e200=95):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))
class BreakoutRetestTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_break_retest_hold(self):
  cs=[c(i,99,100,98,99) for i in range(23)]+[c(23,99,103,99,102),c(24,102,104,99.5,103)]
  s=await BreakoutRetestStrategy().analyze(snap(cs));self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG");self.assertEqual(s.metadata["breakout_level"],100)
 async def test_short_break_retest_hold(self):
  cs=[c(i,101,102,100,101) for i in range(23)]+[c(23,101,101,97,98),c(24,98,100.5,96,97)]
  s=await BreakoutRetestStrategy().analyze(snap(cs,95,100,105));self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_breakout_without_retest(self):
  cs=[c(i,99,100,98,99) for i in range(23)]+[c(23,99,103,99,102),c(24,103,105,102,104)]
  self.assertIsNone(await BreakoutRetestStrategy().analyze(snap(cs)))
 async def test_rejects_retest_that_fails_level(self):
  cs=[c(i,99,100,98,99) for i in range(23)]+[c(23,99,103,99,102),c(24,102,103,97,99)]
  self.assertIsNone(await BreakoutRetestStrategy().analyze(snap(cs)))
if __name__=="__main__":unittest.main()
