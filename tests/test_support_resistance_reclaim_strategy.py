from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.support_resistance_reclaim import SupportResistanceReclaimStrategy

def c(i,o,h,l,cl):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,1000,t+timedelta(hours=1),100000,100,500,50000)

def snap(cs,e20=105,e50=100,e200=95):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))

class SupportResistanceReclaimTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_failed_break_reclaim_hold(self):
  cs=[c(i,100,102,98,100) for i in range(27)]
  cs += [c(27,100,101,95,97),c(28,97,101,96,100),c(29,100,103,99,102)]
  s=await SupportResistanceReclaimStrategy().analyze(snap(cs))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_failed_break_reclaim_hold(self):
  cs=[c(i,100,102,98,100) for i in range(27)]
  cs += [c(27,100,105,99,103),c(28,103,104,99,101),c(29,101,102,97,99)]
  s=await SupportResistanceReclaimStrategy().analyze(snap(cs,95,100,105))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_without_hold_confirmation(self):
  cs=[c(i,100,102,98,100) for i in range(27)]
  cs += [c(27,100,101,95,97),c(28,97,101,96,100),c(29,100,101,97,99)]
  self.assertIsNone(await SupportResistanceReclaimStrategy().analyze(snap(cs)))
 async def test_rejects_without_failed_displacement(self):
  cs=[c(i,100,102,98,100) for i in range(27)]
  cs += [c(27,100,101,98.5,100),c(28,100,101,99,100.5),c(29,100.5,103,100,102)]
  self.assertIsNone(await SupportResistanceReclaimStrategy().analyze(snap(cs)))
if __name__=="__main__":unittest.main()
