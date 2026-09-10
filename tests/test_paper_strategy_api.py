from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import api.paper_strategy_api as paper_strategy_api
from api.app import app
from stage10.paper_strategy_review import (
    PaperReviewStatus,
    PaperStrategyReview,
    PaperStrategyReviewStore,
)

NOW = datetime(2026, 9, 6, 6, tzinfo=timezone.utc)


def test_paper_strategy_reviews_api_is_read_only_and_serializes_metrics():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "reviews.db"
        with mock.patch.dict(
            "os.environ",
            {"PAPER_STRATEGY_REVIEW_DB_PATH": str(path)},
        ):
            store = PaperStrategyReviewStore(path)
            store.upsert(
                PaperStrategyReview(
                    "O",
                    "SL",
                    "S",
                    "1",
                    "H",
                    30,
                    30,
                    10,
                    20,
                    0,
                    Decimal("-0.2"),
                    Decimal("0.6"),
                    Decimal("-7"),
                    Decimal("-45"),
                    Decimal("3"),
                    PaperReviewStatus.PAUSE,
                    "negative evidence",
                    NOW,
                )
            )
            body = TestClient(app).get("/paper-strategies/reviews")
            assert body.status_code == 200
            payload = body.json()
            assert payload["simulation_only"] is True
            assert len(payload["reviews"]) == 1
            row = payload["reviews"][0]
            assert row["research_track"] == "SL"
            assert row["strategy_id"] == "S"
            assert row["status"] == "PAUSE"
            assert row["closed_trades"] == 30
            assert row["average_net_r"] == "-0.2"
            assert row["profit_factor_r"] == "0.6"
            assert row["reason"] == "negative evidence"


def test_strategy_lab_statistics_is_reports_read_only_view():
    snapshot = {
        "summary": {
            "completed": 294,
            "clean_completed": 289,
            "wins": 89,
            "losses": 196,
            "breakeven": 4,
            "total_profit": -38.64,
        },
        "strategies": [
            {
                "label": "LiquiditySweep",
                "total": 50,
                "clean_completed": 40,
                "wins": 20,
                "losses": 20,
                "total_profit": 12.5,
            }
        ],
        "by_setup_reason": [],
        "by_close_reason": [],
        "by_status": [],
        "by_outcome": [{"label": "stop_loss", "total": 104}],
        "by_outcome_group": [{"label": "negative", "total": 196}],
    }

    with mock.patch.object(
        paper_strategy_api,
        "_report_snapshot",
        return_value=snapshot,
    ):
        response = TestClient(app).get("/strategy-lab/statistics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert payload["simulation_only"] is True
    assert payload["research_track"] == "SL"
    assert payload["source"] == "reports"
    assert payload["summary"]["completed"] == 294
    assert payload["summary"]["clean_completed"] == 289
    assert payload["summary"]["total_profit"] == -38.64
    assert len(payload["strategies"]) == 1
    assert payload["strategies"][0]["label"] == "LiquiditySweep"
    assert payload["by_outcome"][0]["label"] == "stop_loss"
