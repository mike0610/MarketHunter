from __future__ import annotations
import unittest
from datetime import datetime,timezone
from models.candle import Candle
from models.market_snapshot import MarketSnapshot
from models.signal import Signal
from pipeline.context import SignalContext
from pipeline.handlers import RiskHandler
from risk.risk_manager import RiskManager

def snapshot():
 t=datetime(2026,1,1,tzinfo=timezone.utc)
 c=Candle(t,100,103,97,100,1000,t,100000,100,500,50000)
 return MarketSnapshot("BTCUSDT",[c],101,100,99,2,1000,103,97)

class StrategyRiskGeometryTests(unittest.IsolatedAsyncioTestCase):
 async def test_strategy_geometry_overrides_legacy_risk(self):
  sig=Signal("BTCUSDT","futures","1h","Test","LONG",90,metadata={"entry":100,"stop_loss":98,"take_profit":106})
  ctx=SignalContext(sig,snapshot())
  await RiskHandler(RiskManager(),10000,1,3).handle(ctx)
  self.assertTrue(ctx.accepted);self.assertEqual(ctx.risk.entry,100);self.assertEqual(ctx.risk.stop_loss,98);self.assertEqual(ctx.risk.take_profit,106);self.assertEqual(ctx.risk.risk_reward,3);self.assertTrue(sig.metadata["strategy_risk_geometry_applied"])
 async def test_legacy_signal_keeps_risk_manager_geometry(self):
  sig=Signal("BTCUSDT","futures","1h","Legacy","LONG",90)
  ctx=SignalContext(sig,snapshot())
  await RiskHandler(RiskManager(),10000,1,3).handle(ctx)
  self.assertTrue(ctx.accepted);self.assertNotIn("strategy_risk_geometry_applied",sig.metadata)
 async def test_invalid_long_geometry_is_rejected(self):
  sig=Signal("BTCUSDT","futures","1h","Test","LONG",90,metadata={"entry":100,"stop_loss":102,"take_profit":106})
  ctx=SignalContext(sig,snapshot())
  await RiskHandler(RiskManager(),10000,1,3).handle(ctx)
  self.assertFalse(ctx.accepted);self.assertIsNone(ctx.risk)
 async def test_invalid_short_geometry_is_rejected(self):
  sig=Signal("BTCUSDT","futures","1h","Test","SHORT",90,metadata={"entry":100,"stop_loss":98,"take_profit":94})
  ctx=SignalContext(sig,snapshot())
  await RiskHandler(RiskManager(),10000,1,3).handle(ctx)
  self.assertFalse(ctx.accepted);self.assertIsNone(ctx.risk)
if __name__=="__main__":unittest.main()
