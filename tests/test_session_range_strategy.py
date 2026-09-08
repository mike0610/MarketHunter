from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.session_range import SessionRangeStrategy

def c(i,o,h,l,cl):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,1000,t+timedelta(hours=1),100000,100,500,50000)

def snap(cs,e20=105,e50=100,e200=95,atr=2):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,atr,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))

class SessionRangeTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_after_completed_asia_range_break(self):
  pre=[c(i,100,101,99,100) for i in range(24)]
  asia=[c(24+i,100,102,98,100) for i in range(8)]
  trigger=c(32,100,104,99,103)
  s=await SessionRangeStrategy().analyze(snap(pre+asia+[trigger]))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_after_completed_asia_range_break(self):
  pre=[c(i,100,101,99,100) for i in range(24)]
  asia=[c(24+i,100,102,98,100) for i in range(8)]
  trigger=c(32,100,101,96,97)
  s=await SessionRangeStrategy().analyze(snap(pre+asia+[trigger],95,100,105))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_before_asia_window_complete(self):
  pre=[c(i,100,101,99,100) for i in range(24)]
  partial=[c(24+i,100,102,98,100) for i in range(4)]
  trigger=c(28,100,104,99,103)
  self.assertIsNone(await SessionRangeStrategy().analyze(snap(pre+partial+[trigger])))
 async def test_rejects_no_boundary_break(self):
  pre=[c(i,100,101,99,100) for i in range(24)]
  asia=[c(24+i,100,102,98,100) for i in range(8)]
  trigger=c(32,100,101.5,98.5,100.5)
  self.assertIsNone(await SessionRangeStrategy().analyze(snap(pre+asia+[trigger])))
if __name__=="__main__":unittest.main()
