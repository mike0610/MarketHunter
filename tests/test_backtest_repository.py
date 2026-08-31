from pathlib import Path

from backtesting.repository import BacktestRepository


def test_backtest_repository_persists_across_instances(tmp_path: Path):
    db_path = tmp_path / "backtests.db"
    first = BacktestRepository(db_path)
    record = {
        "id": "run-1",
        "label": "Persistence check",
        "created_at": "2026-08-31T04:50:00+00:00",
        "result": {
            "initial_balance": 10000.0,
            "final_balance": 10125.0,
            "total_return": 1.25,
            "trades": 2,
            "wins": 1,
            "losses": 1,
            "win_rate": 50.0,
            "profit_factor": 2.0,
            "max_drawdown": 0.5,
            "sharpe": 0.0,
            "equity_curve": [10000.0, 10200.0, 10125.0],
        },
    }

    first.save(record)

    second = BacktestRepository(db_path)
    loaded = second.get("run-1")

    assert loaded == record
    assert second.list_recent() == [record]
