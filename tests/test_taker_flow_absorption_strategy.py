from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.taker_flow_absorption import TakerFlowAbsorptionStrategy

def c(i,o,h,l,cl,vol=1000,buy=500):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,vol,t+timedelta(hours=1),100000,100,buy,buy*100)

def snap(cs,atr=2.0):
 return MarketSnapshot("BTCUSDT",cs,105,100,95,atr,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))

class TakerFlowAbsorptionTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_sell_flow_absorbed_and_low_reclaimed(self):
  cs=[c(i,100,102,98,100) for i in range(22)]
  cs += [c(22,100,101,97,99,1000,300),c(23,99,100,96,98.5,1000,350),c(24,98.5,101,97,100,1000,350)]
  s=await TakerFlowAbsorptionStrategy().analyze(snap(cs))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG");self.assertLessEqual(s.metadata["taker_buy_share"],.38)
 async def test_short_buy_flow_absorbed_and_high_rejected(self):
  cs=[c(i,100,102,98,100) for i in range(22)]
  cs += [c(22,100,103,99,101,1000,700),c(23,101,104,100,101.5,1000,650),c(24,101.5,103,99,100,1000,650)]
  s=await TakerFlowAbsorptionStrategy().analyze(snap(cs))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT");self.assertGreaterEqual(s.metadata["taker_buy_share"],.62)
 async def test_rejects_balanced_flow(self):
  cs=[c(i,100,102,98,100) for i in range(22)]
  cs += [c(22,100,101,97,99,1000,500),c(23,99,100,96,98.5,1000,500),c(24,98.5,101,97,100,1000,500)]
  self.assertIsNone(await TakerFlowAbsorptionStrategy().analyze(snap(cs)))
 async def test_rejects_sell_flow_when_price_accepts_lower(self):
  cs=[c(i,100,102,98,100) for i in range(22)]
  cs += [c(22,100,101,97,98,1000,300),c(23,98,99,95,96,1000,300),c(24,96,97,93,94,1000,300)]
  self.assertIsNone(await TakerFlowAbsorptionStrategy().analyze(snap(cs)))
if __name__=="__main__":unittest.main()
