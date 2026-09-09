from datetime import datetime, timezone
from types import SimpleNamespace
from experiment1 import direct_positive_strategy_bridge as bridge
from experiment1.engine import Experiment1Engine
from research.models.trade_status import TradeStatus

T0=datetime(2026,9,9,5,0,tzinfo=timezone.utc)

class FakeRepo:
    trades=[]
    def __init__(self,path): pass
    def list_all(self): return list(self.trades)
    def close(self): pass

def test_forward_only_and_dedup(tmp_path,monkeypatch):
    monkeypatch.setenv(bridge.ENV_ENABLED,"1")
    monkeypatch.setenv(bridge.ENV_CHECKPOINT,str(tmp_path/"checkpoint.json"))
    monkeypatch.setattr(bridge,"ResearchRepository",FakeRepo)
    engine=Experiment1Engine(tmp_path/"experiment1.db")
    FakeRepo.trades=[]
    first=bridge.run_direct_positive_strategy_bridge(engine,now=T0)
    assert first.bootstrapped and first.queued==0
    FakeRepo.trades=[SimpleNamespace(id="t1",symbol="BTCUSDT",market="futures",strategy="Compression",direction="LONG",stop_loss=95.0,take_profit=110.0,status=TradeStatus.ACTIVE,created_at=T0)]
    second=bridge.run_direct_positive_strategy_bridge(engine,now=T0)
    third=bridge.run_direct_positive_strategy_bridge(engine,now=T0)
    assert second.queued==1
    assert third.queued==0 and third.skipped_existing==1
    assert engine.trading_decision_inbox_status("research-direct:t1") is not None
