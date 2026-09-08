from __future__ import annotations
import unittest
from datetime import datetime,timedelta,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from strategies.failed_auction import FailedAuctionStrategy

def c(i,o,h,l,cl):
 t=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(hours=i)
 return Candle(t,o,h,l,cl,1000,t+timedelta(hours=1),100000,100,500,50000)

def snap(cs,e20=105,e50=100,e200=95):
 return MarketSnapshot("BTCUSDT",cs,e20,e50,e200,2,1000,max(x.high for x in cs[-20:]),min(x.low for x in cs[-20:]))

class FailedAuctionTests(unittest.IsolatedAsyncioTestCase):
 async def test_long_after_two_closes_below_range_then_return(self):
  cs=[c(i,100,102,98,100) for i in range(29)]
  cs += [c(29,99,100,96,97),c(30,97,99,95,96.5),c(31,96.5,101,96,100)]
  s=await FailedAuctionStrategy().analyze(snap(cs))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"LONG")
 async def test_short_after_two_closes_above_range_then_return(self):
  cs=[c(i,100,102,98,100) for i in range(29)]
  cs += [c(29,101,104,100,103),c(30,103,105,102,104),c(31,104,104,99,101)]
  s=await FailedAuctionStrategy().analyze(snap(cs,95,100,105))
  self.assertIsNotNone(s);self.assertEqual(s.direction,"SHORT")
 async def test_rejects_single_close_false_breakout(self):
  cs=[c(i,100,102,98,100) for i in range(29)]
  cs += [c(29,99,100,96,97),c(30,97,100,98.5,99),c(31,99,101,98.5,100)]
  self.assertIsNone(await FailedAuctionStrategy().analyze(snap(cs)))
 async def test_rejects_without_return_inside_range(self):
  cs=[c(i,100,102,98,100) for i in range(29)]
  cs += [c(29,99,100,96,97),c(30,97,99,95,96.5),c(31,96.5,98,95.5,97)]
  self.assertIsNone(await FailedAuctionStrategy().analyze(snap(cs)))
if __name__=="__main__":unittest.main()
