from __future__ import annotations

import tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from api.app import app
from stage10.paper_strategy_review import PaperReviewStatus,PaperStrategyReview,PaperStrategyReviewStore

NOW=datetime(2026,9,6,6,tzinfo=timezone.utc)

def test_paper_strategy_reviews_api_is_read_only_and_serializes_metrics():
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"reviews.db"
        with mock.patch.dict("os.environ",{"PAPER_STRATEGY_REVIEW_DB_PATH":str(path)}):
            store=PaperStrategyReviewStore(path)
            store.upsert(PaperStrategyReview(
                "O","SL","S","1","H",30,30,10,20,0,Decimal("-0.2"),Decimal("0.6"),
                Decimal("-7"),Decimal("-45"),Decimal("3"),PaperReviewStatus.PAUSE,
                "negative evidence",NOW))
            body=TestClient(app).get("/paper-strategies/reviews")
            assert body.status_code==200
            payload=body.json()
            assert payload["simulation_only"] is True
            assert len(payload["reviews"])==1
            row=payload["reviews"][0]
            assert row["research_track"]=="SL"
            assert row["strategy_id"]=="S"
            assert row["status"]=="PAUSE"
            assert row["closed_trades"]==30
            assert row["average_net_r"]=="-0.2"
            assert row["profit_factor_r"]=="0.6"
            assert row["reason"]=="negative evidence"

def test_strategy_lab_statistics_is_one_read_only_sl_view():
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"reviews.db"
        with mock.patch.dict("os.environ",{"PAPER_STRATEGY_REVIEW_DB_PATH":str(path)}):
            store=PaperStrategyReviewStore(path)
            store.upsert(PaperStrategyReview(
                "SL1","SL","Sweep","1","H1",12,12,7,5,0,Decimal("0.25"),Decimal("1.4"),
                Decimal("-2"),Decimal("18"),Decimal("2"),PaperReviewStatus.PAPER_ACTIVE,
                "collecting evidence",NOW))
            store.upsert(PaperStrategyReview(
                "G1","GIL","Trend","1","H2",20,20,12,8,0,Decimal("0.15"),Decimal("1.2"),
                Decimal("-1"),Decimal("30"),Decimal("3"),PaperReviewStatus.PAPER_ACTIVE,
                "collecting evidence",NOW))
            response=TestClient(app).get("/strategy-lab/statistics")
            assert response.status_code==200
            payload=response.json()
            assert payload["simulation_only"] is True
            assert payload["research_track"]=="SL"
            assert payload["summary"]["strategies"]==1
            assert payload["summary"]["closed_trades"]==12
            assert payload["summary"]["wins"]==7
            assert payload["summary"]["losses"]==5
            assert payload["summary"]["net_pnl"]=="18"
            assert len(payload["strategies"])==1
            assert payload["strategies"][0]["strategy_id"]=="Sweep"
            assert payload["strategies"][0]["research_track"]=="SL"
