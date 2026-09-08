from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.liquidity_sweep_reclaim import LiquiditySweepReclaimStrategy
def c(i,o,h,l,cl):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,1000,t+timedelta(hours=1),100000,100,500,50000)
def snap(cs,e20=105,e50=100,e200=95):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))
class LiquiditySweepReclaimTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_needs_sweep_reclaim_then_confirmation(self):
  cs=[c(i,100,102,98,100) for i in range(23)]+[c(23,100,101,96,99),c(24,99,103,98,102)]
  s=await LiquiditySweepReclaimStrategy().analyze(snap(cs));self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_needs_sweep_reclaim_then_confirmation(self):
  cs=[c(i,100,102,98,100) for i in range(23)]+[c(23,100,104,99,101),c(24,101,102,97,98)]
  s=await LiquiditySweepReclaimStrategy().analyze(snap(cs,95,100,105));self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_sweep_without_separate_confirmation(self):
  cs=[c(i,100,102,98,100) for i in range(23)]+[c(23,100,101,96,99),c(24,99,100,98,99.5)]
  self.assertIsNone(await LiquiditySweepReclaimStrategy().analyze(snap(cs)))
 async def test_rejects_confirmation_without_prior_sweep(self):
  cs=[c(i,100,102,98,100) for i in range(23)]+[c(23,100,101,98.5,100),c(24,100,103,99,102)]
  self.assertIsNone(await LiquiditySweepReclaimStrategy().analyze(snap(cs)))
if __name__=="__main__":unittest.main()
