from pathlib import Path


def test_strategy_backtest_contract_present():
    source = Path("api/backtest_api.py").read_text(encoding="utf-8")
    assert '@router.post("/run/strategy")' in source
    assert "BreakoutStrategy" in source
    assert "MarketDataService" in source
    assert "StrategyReplayEngine" in source
