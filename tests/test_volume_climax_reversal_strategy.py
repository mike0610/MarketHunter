from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.volume_climax_reversal import VolumeClimaxReversalStrategy
def c(i,o,h,l,cl,vol=1000):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,vol,t+timedelta(hours=1),100000,100,vol*.5,vol*50)
def snap(cs):
 return MarketSnapshot("BTCUSDT",cs,100,100,100,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))
class VolumeClimaxReversalTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_climax_rejection_confirmed(self):
  hist=[c(i,100,101,99,100) for i in range(28)]
  climax=c(28,99,100,94,98.5,2500); confirm=c(29,98.5,101,98,100)
  s=await VolumeClimaxReversalStrategy().analyze(snap(hist+[climax,confirm]))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_climax_rejection_confirmed(self):
  hist=[c(i,100,101,99,100) for i in range(28)]
  climax=c(28,101,106,100,101.5,2500); confirm=c(29,101.5,102,99,100)
  s=await VolumeClimaxReversalStrategy().analyze(snap(hist+[climax,confirm]))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_normal_volume(self):
  hist=[c(i,100,101,99,100) for i in range(28)]
  climax=c(28,99,100,94,98.5,1200); confirm=c(29,98.5,101,98,100)
  self.assertIsNone(await VolumeClimaxReversalStrategy().analyze(snap(hist+[climax,confirm])))
 async def test_rejects_without_confirmation(self):
  hist=[c(i,100,101,99,100) for i in range(28)]
  climax=c(28,99,100,94,98.5,2500); confirm=c(29,98.5,99,96,97)
  self.assertIsNone(await VolumeClimaxReversalStrategy().analyze(snap(hist+[climax,confirm])))
if __name__=="__main__":unittest.main()
