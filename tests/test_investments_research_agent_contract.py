from datetime import datetime, timedelta, timezone
from decimal import Decimal
import tempfile
from pathlib import Path

import pytest

from experiment1.models import AccountKind
from investments.autonomous_loop import (
    AutonomousInvestmentStore,
    InvestmentResearchDecision,
)
from investments.research_agent_contract import (
    GILResearchEvidence,
    GILResearchOutcome,
    GILResearchRequest,
    GILResearchResult,
    ingest_gil_research_result,
)
from investments.research_queue import (
    InvestmentResearchQueue,
    InvestmentResearchQueueItem,
)
from investments.research_worker import InvestmentResearchWorker


NOW = datetime(2026, 9, 6, 16, tzinfo=timezone.utc)


def _claimed(root: Path):
    queue = InvestmentResearchQueue(root / "research.db")
    queue.enqueue(
        InvestmentResearchQueueItem(
            "obj-1",
            "VWCE",
            NOW,
            "seed:fresh",
            Decimal("90"),
        )
    )
    worker = InvestmentResearchWorker(queue)
    claim = worker.claim_next(now=NOW)
    assert claim is not None
    return queue, worker, claim


def _result(decision=InvestmentResearchDecision.WAIT, **overrides):
    data = dict(
        candidate_id="obj-1",
        symbol="VWCE",
        outcome=GILResearchOutcome.DECISION,
        agent_reference="gil-agent:run-1",
        completed_at=NOW + timedelta(minutes=5),
        evidence=(
            GILResearchEvidence(
                "primary:https://example.test/source",
                NOW + timedelta(minutes=4),
            ),
        ),
        account=AccountKind.INVESTMENTS_BALANCED,
        decision=decision,
        investment_attractiveness=Decimal("0.80"),
        executability=Decimal("0.70"),
        thesis="fresh evidence-backed thesis",
        counter_thesis="fresh evidence-backed counter-thesis",
        revisit_condition=(
            "revisit after valuation changes"
            if decision is InvestmentResearchDecision.WAIT
            else None
        ),
        blocker=None,
    )
    data.update(overrides)
    return GILResearchResult(**data)


def test_claim_converts_to_machine_research_request_without_decision_authority():
    with tempfile.TemporaryDirectory() as td:
        _, _, claim = _claimed(Path(td))
        request = GILResearchRequest.from_claim(claim)
        assert request.candidate_id == "obj-1"
        assert request.symbol == "VWCE"
        assert not hasattr(request, "decision")
        assert not hasattr(request, "thesis")


def test_fresh_wait_result_is_durable_and_creates_no_order_surface():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        queue, worker, claim = _claimed(root)
        store = AutonomousInvestmentStore(root / "decisions.db")
        record = ingest_gil_research_result(
            worker=worker,
            store=store,
            claim=claim,
            result=_result(),
            max_evidence_age=timedelta(days=7),
        )
        assert record is not None
        assert record.decision is InvestmentResearchDecision.WAIT
        assert len(store.rows()) == 1
        assert queue.pending() == ()
        assert not hasattr(record, "order_intent")


def test_reject_is_durable_but_never_promoted_to_order_action():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _, worker, claim = _claimed(root)
        store = AutonomousInvestmentStore(root / "decisions.db")
        record = ingest_gil_research_result(
            worker=worker,
            store=store,
            claim=claim,
            result=_result(
                decision=InvestmentResearchDecision.REJECT,
                revisit_condition=None,
            ),
            max_evidence_age=timedelta(days=7),
        )
        assert record is not None
        assert record.decision is InvestmentResearchDecision.REJECT


def test_blocked_evidence_finishes_without_investment_decision():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _, worker, claim = _claimed(root)
        store = AutonomousInvestmentStore(root / "decisions.db")
        blocked = GILResearchResult(
            candidate_id="obj-1",
            symbol="VWCE",
            outcome=GILResearchOutcome.BLOCKED_EVIDENCE,
            agent_reference="gil-agent:run-blocked",
            completed_at=NOW + timedelta(minutes=5),
            evidence=(
                GILResearchEvidence(
                    "source:https://example.test/unavailable",
                    NOW + timedelta(minutes=4),
                ),
            ),
            blocker="authoritative access evidence unavailable",
        )
        assert (
            ingest_gil_research_result(
                worker=worker,
                store=store,
                claim=claim,
                result=blocked,
                max_evidence_age=timedelta(days=7),
            )
            is None
        )
        assert store.rows() == ()


def test_stale_or_mismatched_result_fails_closed_and_is_not_recorded():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _, worker, claim = _claimed(root)
        store = AutonomousInvestmentStore(root / "decisions.db")
        stale = _result(
            evidence=(
                GILResearchEvidence(
                    "stale:https://example.test/old",
                    NOW - timedelta(days=30),
                ),
            )
        )
        with pytest.raises(ValueError, match="stale"):
            ingest_gil_research_result(
                worker=worker,
                store=store,
                claim=claim,
                result=stale,
                max_evidence_age=timedelta(days=7),
            )
        assert store.rows() == ()

        with pytest.raises(ValueError, match="symbol mismatch"):
            ingest_gil_research_result(
                worker=worker,
                store=store,
                claim=claim,
                result=_result(symbol="SPY"),
                max_evidence_age=timedelta(days=7),
            )
        assert store.rows() == ()


def test_duplicate_delivery_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _, worker, claim = _claimed(root)
        store = AutonomousInvestmentStore(root / "decisions.db")
        result = _result(
            decision=InvestmentResearchDecision.HOLD,
            revisit_condition=None,
        )
        first = ingest_gil_research_result(
            worker=worker,
            store=store,
            claim=claim,
            result=result,
            max_evidence_age=timedelta(days=7),
        )
        second = ingest_gil_research_result(
            worker=worker,
            store=store,
            claim=claim,
            result=result,
            max_evidence_age=timedelta(days=7),
        )
        assert first is not None
        assert second is None
        assert len(store.rows()) == 1


def test_non_investment_account_and_wait_without_revisit_are_rejected():
    with pytest.raises(ValueError):
        _result(account=AccountKind.SPOT)
    with pytest.raises(ValueError, match="WAIT requires"):
        _result(revisit_condition=None)
