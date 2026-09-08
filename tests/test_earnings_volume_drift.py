import unittest
from datetime import datetime, date, timezone
from decimal import Decimal

from market_data.foundation import MarketBar, MarketInstrument, MarketSeries
from market_data.twelve_data_earnings import EarningsEvent
from research.earnings_volume_drift import EarningsDriftDirection, detect_earnings_volume_drift_signals


def bar(day, o, h, l, c, v):
    return MarketBar(datetime(2026,1,day,tzinfo=timezone.utc),Decimal(str(o)),Decimal(str(h)),Decimal(str(l)),Decimal(str(c)),Decimal(str(v)))


class EarningsVolumeDriftTests(unittest.TestCase):
    def series(self,last):
        bars=[bar(i+1,100,101,99,100,100) for i in range(20)]
        bars.append(last)
        return MarketSeries(MarketInstrument("AAPL","US_STOCK","USD"),"1d",tuple(bars),"TEST","ref",last.timestamp,last.timestamp)

    def event(self):
        return (EarningsEvent("AAPL",date(2026,1,21),"TWELVE_DATA","earnings-ref"),)

    def test_long_signal(self):
        x=detect_earnings_volume_drift_signals(self.series(bar(21,101,106,100,105,300)),self.event())
        self.assertEqual(len(x),1); self.assertEqual(x[0].direction,EarningsDriftDirection.LONG)
        self.assertEqual(x[0].signal_bar_high,Decimal("106")); self.assertEqual(x[0].signal_bar_low,Decimal("100"))

    def test_short_signal(self):
        x=detect_earnings_volume_drift_signals(self.series(bar(21,99,100,94,95,400)),self.event())
        self.assertEqual(len(x),1); self.assertEqual(x[0].direction,EarningsDriftDirection.SHORT)

    def test_requires_earnings_and_three_x_volume(self):
        s=self.series(bar(21,101,106,100,105,299))
        self.assertEqual(detect_earnings_volume_drift_signals(s,self.event()),())
        s2=self.series(bar(21,101,106,100,105,300))
        self.assertEqual(detect_earnings_volume_drift_signals(s2,()),())


if __name__=="__main__": unittest.main()
