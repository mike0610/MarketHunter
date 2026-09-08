import unittest
from datetime import datetime, timezone, date
from decimal import Decimal
from market_data.foundation import MarketBar,MarketInstrument,MarketSeries
from research.earnings_volume_drift import EarningsDriftDirection,EarningsDriftSignal
from research.earnings_volume_drift_execution import simulate_signal

def b(i,o,h,l,c):
 return MarketBar(datetime(2026,1,1,tzinfo=timezone.utc).replace(day=i+1),Decimal(str(o)),Decimal(str(h)),Decimal(str(l)),Decimal(str(c)),Decimal("100"))

class ExecutionTests(unittest.TestCase):
 def series(self,tail):
  bars=[b(i,100,101,99,100) for i in range(21)]+tail
  return MarketSeries(MarketInstrument("AAPL","US_STOCK","USD"),"1d",tuple(bars),"T","r",bars[-1].timestamp,bars[-1].timestamp)
 def sig(self,d=EarningsDriftDirection.LONG):
  return EarningsDriftSignal("AAPL",date(2026,1,21),d,Decimal("105"),Decimal("95"),Decimal("3"),"e")
 def test_long_gap_fill_and_structural_exit(self):
  s=self.series([b(21,106,108,100,107),b(22,94,96,93,95)])
  t=simulate_signal(s,self.sig())
  self.assertEqual(t.entry_price,Decimal("106"));self.assertEqual(t.exit_price,Decimal("94"));self.assertEqual(t.exit_reason,"STRUCTURAL_INVALIDATION")
 def test_ambiguous_entry_bar_rejected(self):
  s=self.series([b(21,100,106,94,101)])
  self.assertIsNone(simulate_signal(s,self.sig()))
 def test_expiry_after_three_sessions(self):
  s=self.series([b(21,100,104,96,101),b(22,100,104,96,101),b(23,100,104,96,101),b(24,106,108,100,107)])
  self.assertIsNone(simulate_signal(s,self.sig()))
if __name__=="__main__":unittest.main()
