from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.volatility_expansion import VolatilityExpansionStrategy

def c(i,o,h,l,cl):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,1000,t+timedelta(hours=1),100000,100,500,50000)

def snap(cs,e20=105,e50=100,e200=95,atr=2.0):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,atr,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))

class VolatilityExpansionTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_quiet_then_expansion(self):
  base=[c(i,100,104,96,100) for i in range(22)]
  quiet=[c(22+i,100,101,99,100) for i in range(12)]
  trig=c(34,100,105,99.5,104.5)
  s=await VolatilityExpansionStrategy().analyze(snap(base+quiet+[trig]))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_quiet_then_expansion(self):
  base=[c(i,100,104,96,100) for i in range(22)]
  quiet=[c(22+i,100,101,99,100) for i in range(12)]
  trig=c(34,100,100.5,95,95.5)
  s=await VolatilityExpansionStrategy().analyze(snap(base+quiet+[trig],95,100,105))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_without_quiet_regime(self):
  base=[c(i,100,104,96,100) for i in range(22)]
  noisy=[c(22+i,100,104,96,100) for i in range(12)]
  trig=c(34,100,105,99,104.5)
  self.assertIsNone(await VolatilityExpansionStrategy().analyze(snap(base+noisy+[trig])))
 async def test_rejects_expansion_without_range_break(self):
  base=[c(i,100,104,96,100) for i in range(22)]
  quiet=[c(22+i,100,101,99,100) for i in range(12)]
  trig=c(34,100,102,98,100.5)
  self.assertIsNone(await VolatilityExpansionStrategy().analyze(snap(base+quiet+[trig])))
if __name__=="__main__":unittest.main()
