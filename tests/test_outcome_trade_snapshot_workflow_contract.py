from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/publish-outcome-trade-snapshot.yml")


def test_trade_snapshot_workflow_is_read_only_against_production() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "/research/trades" in text
    assert "limit = 200" in text
    assert "trade population changed during capture" in text
    assert "incomplete or duplicate trade population" in text
    assert "127.0.0.1:8000" in text

    forbidden = (
        "systemctl restart",
        "systemctl stop",
        "systemctl start",
        "sqlite3 ",
        "git pull",
        "git checkout master",
    )
    for token in forbidden:
        assert token not in text


def test_trade_snapshot_workflow_publishes_provenance() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert '"captured_at_utc"' in text
    assert '"source_revision"' in text
    assert '"sha256"' in text
    assert '"byte_count"' in text
    assert "outcome-intelligence-snapshots" in text
    assert "data/outcome_intelligence/latest" in text
