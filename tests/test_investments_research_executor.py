from datetime import datetime, timezone
from decimal import Decimal

import pytest

from experiment1.models import AccountKind
from investments.autonomous_loop import AutonomousInvestmentStore
from investments.research_executor import USInvestmentResearchExecutor
from investments.research_queue import InvestmentResearchQueue, InvestmentResearchQueueItem
from investments.research_worker import InvestmentResearchWorker


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


class Identity:
    def resolve(self, symbol):
        return type("I", (), {"cik": "0000320193"})()


class Evidence:
    def fetch(self, cik):
        return type("E", (), {"as_source": lambda self: {
            "reference": "sec:companyfacts:CIK0000320193",
            "authority": "SEC",
            "observed_at": NOW.isoformat(),
            "content": {"entity_name": "Apple Inc.", "facts": {}},
        }})()


class Reasoner:
    def __init__(self, result):
        self.result = result
    def analyze(self, request, *, evidence_bundle):
        assert evidence_bundle["sources"][0]["authority"] == "SEC"
        return self.result


def setup(tmp_path):
    q = InvestmentResearchQueue(tmp_path / "q.db")
    q.enqueue(InvestmentResearchQueueItem("x", "AAPL", NOW, "seed:fresh", Decimal("0.9")))
    return q, InvestmentResearchWorker(q), AutonomousInvestmentStore(tmp_path / "r.db")


def test_blocked_evidence_creates_zero_decision(tmp_path):
    q, worker, store = setup(tmp_path)
    x = USInvestmentResearchExecutor(worker, store, Identity(), Evidence(), Reasoner({
        "outcome": "BLOCKED_EVIDENCE", "blocker": "valuation evidence missing"
    }))
    assert x.run_once() is None
    assert q.pending() == ()


def test_wait_is_durable_but_zero_order_authority(tmp_path):
    q, worker, store = setup(tmp_path)
    x = USInvestmentResearchExecutor(worker, store, Identity(), Evidence(), Reasoner({
        "outcome": "DECISION",
        "decision": "WAIT",
        "account": AccountKind.INVESTMENTS_GROWTH.value,
        "investment_attractiveness": "0.8",
        "executability": "0.9",
        "thesis": "Evidence-backed thesis",
        "counter_thesis": "Evidence-backed counter thesis",
        "revisit_condition": "Next filing",
    }))
    record = x.run_once()
    assert record is not None
    assert record.decision.value == "WAIT"
    assert record.revisit_condition == "Next filing"


def test_provider_failure_marks_blocked_not_decided(tmp_path):
    q, worker, store = setup(tmp_path)
    class Broken:
        def analyze(self, *args, **kwargs):
            raise RuntimeError("offline")
    x = USInvestmentResearchExecutor(worker, store, Identity(), Evidence(), Broken())
    with pytest.raises(RuntimeError, match="offline"):
        x.run_once()
    assert q.pending() == ()
