"""Regression tests for safe repair of stale research stop outcomes."""
from datetime import datetime, timezone

from research.storage.repository import ResearchRepository


def _insert(repo, trade_id, *, reason, profit, group, locked=0):
    with repo.connection:
        repo.connection.execute(
            """INSERT INTO research_trades (
                id, symbol, market, timeframe, strategy, direction,
                entry_price, stop_loss, take_profit, probability, score,
                reasons, status, created_at, close_reason, profit_amount,
                profit_percent, outcome_group, outcome_type, outcome_locked
            ) VALUES (?, 'BTCUSDT', 'futures', '1h', 'TrendPullback', 'LONG',
                      100, 95, 115, 80, 80, '[]', 'closed', ?, ?, ?, ?, ?, 'stop_loss', ?)""",
            (trade_id, datetime.now(timezone.utc).isoformat(), reason,
             profit, profit, group, locked),
        )


def test_repairs_only_unlocked_stale_stop_groups(tmp_path):
    repo = ResearchRepository(str(tmp_path / "research.db"))
    _insert(repo, "profitable", reason="LIVE_STOP_LOSS", profit=1.25, group="negative")
    _insert(repo, "neutral", reason="SL", profit=0, group="negative")
    _insert(repo, "locked", reason="SL", profit=2, group="negative", locked=1)
    _insert(repo, "correct", reason="SL", profit=-2, group="negative")
    _insert(repo, "unknown", reason="MANUAL_CLEANUP: test", profit=3, group="excluded")
    _insert(repo, "cleanup", reason="MANUAL_CLEANUP: stop_loss legacy", profit=3, group="negative")
    _insert(repo, "manual", reason="SL", profit=3, group="negative")
    with repo.connection:
        repo.connection.execute(
            "UPDATE research_trades SET outcome_type = ?, outcome_note = ? WHERE id = ?",
            ("invalid_legacy", "manual review pending", "manual"),
        )
    repo.connection.close()

    repaired = ResearchRepository(str(tmp_path / "research.db"))
    rows = {r["id"]: r for r in repaired.connection.execute(
        "SELECT * FROM research_trades"
    ).fetchall()}
    assert rows["profitable"]["outcome_group"] == "positive"
    assert rows["neutral"]["outcome_group"] == "neutral"
    assert rows["locked"]["outcome_group"] == "negative"
    assert rows["correct"]["outcome_group"] == "negative"
    assert rows["unknown"]["outcome_group"] == "excluded"
    assert rows["cleanup"]["outcome_group"] == "negative"
    assert rows["manual"]["outcome_group"] == "negative"
    assert rows["manual"]["outcome_type"] == "invalid_legacy"
    assert rows["manual"]["outcome_note"] == "manual review pending"
    for trade_id, pnl in (("profitable", 1.25), ("neutral", 0),
                          ("locked", 2), ("correct", -2), ("unknown", 3), ("cleanup", 3), ("manual", 3)):
        assert rows[trade_id]["profit_amount"] == pnl
        assert rows[trade_id]["status"] == "closed"
    repaired.connection.close()
