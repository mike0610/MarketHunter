from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.volume_confirmed_breakout import VolumeConfirmedBreakoutStrategy
def c(i,o,h,l,cl,vol=1000,trades=100):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,vol,t+timedelta(hours=1),100000,trades,vol*.5,vol*50)
def snap(cs,e20=105,e50=100,e200=95):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))
class VolumeConfirmedBreakoutTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_with_volume_and_trade_participation(self):
  cs=[c(i,100,102,98,100) for i in range(29)]+[c(29,100,105,99,104,1700,150)]
  s=await VolumeConfirmedBreakoutStrategy().analyze(snap(cs));self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_with_volume_and_trade_participation(self):
  cs=[c(i,100,102,98,100) for i in range(29)]+[c(29,100,101,95,96,1700,150)]
  s=await VolumeConfirmedBreakoutStrategy().analyze(snap(cs,95,100,105));self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_breakout_without_relative_volume(self):
  cs=[c(i,100,102,98,100) for i in range(29)]+[c(29,100,105,99,104,1200,150)]
  self.assertIsNone(await VolumeConfirmedBreakoutStrategy().analyze(snap(cs)))
 async def test_rejects_breakout_without_trade_participation(self):
  cs=[c(i,100,102,98,100) for i in range(29)]+[c(29,100,105,99,104,1700,110)]
  self.assertIsNone(await VolumeConfirmedBreakoutStrategy().analyze(snap(cs)))
if __name__=="__main__":unittest.main()
