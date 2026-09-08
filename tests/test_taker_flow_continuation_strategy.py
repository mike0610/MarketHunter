from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.taker_flow_continuation import TakerFlowContinuationStrategy
def c(i,o,h,l,cl,vol=1000,buy=500):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,vol,t+timedelta(hours=1),100000,100,buy,buy*100)
def snap(cs,e20=105,e50=100,e200=95):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))
class TakerFlowContinuationTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_flow_and_price_accept_higher(self):
  cs=[c(i,100,102,98,100) for i in range(22)]+[c(22,100,102,99,101,1000,700),c(23,101,103,100,102,1000,680),c(24,102,105,101,104,1000,650)]
  s=await TakerFlowContinuationStrategy().analyze(snap(cs));self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_flow_and_price_accept_lower(self):
  cs=[c(i,100,102,98,100) for i in range(22)]+[c(22,100,101,98,99,1000,300),c(23,99,100,97,98,1000,320),c(24,98,99,95,96,1000,350)]
  s=await TakerFlowContinuationStrategy().analyze(snap(cs,95,100,105));self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_flow_without_price_expansion(self):
  cs=[c(i,100,102,98,100) for i in range(22)]+[c(22,100,101,99,100.2,1000,700),c(23,100.2,101,99.5,100.3,1000,700),c(24,100.3,101,99.8,100.4,1000,700)]
  self.assertIsNone(await TakerFlowContinuationStrategy().analyze(snap(cs)))
 async def test_rejects_breakout_without_flow_confirmation(self):
  cs=[c(i,100,102,98,100) for i in range(22)]+[c(22,100,102,99,101,1000,500),c(23,101,103,100,102,1000,500),c(24,102,105,101,104,1000,500)]
  self.assertIsNone(await TakerFlowContinuationStrategy().analyze(snap(cs)))
if __name__=="__main__":unittest.main()
