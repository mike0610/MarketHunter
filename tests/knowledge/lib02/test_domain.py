import dataclasses
import pytest

from knowledge.lib02 import (
    Program,
    ResearchQuestion,
    ContinuityCapsule,
    Source,
    Version,
    Claim,
    Coverage,
    CoverageState,
    ExaminationResult,
    ReopenConditionError,
)


def test_immutable_domain_objects():
    src = Source(name="feed", version="v1")
    ver = Version(value="1.0")
    claim = Claim(claim_id="c1", semantic="S", source=src)

    with pytest.raises(dataclasses.FrozenInstanceError):
        claim.semantic = "X"

    cap = ContinuityCapsule(routing_snapshots=("r1", "r2"))
    assert cap.routing_snapshots == ("r1", "r2")


def test_reopen_condition_enforced():
    rq = ResearchQuestion(question_id="q1", owner="alice", status="CLOSED")
    with pytest.raises(ReopenConditionError):
        rq.reopen(None)

    cond = type("C", (), {"reason": "new info"})()
    reopened = rq.reopen(cond)
    assert reopened.status == "OPEN"


def test_coverage_and_examination_separation():
    s = Source(name="s", version="v2")
    v = Version(value="v2")
    cov = Coverage(source=s, version=v, range_start=0, range_end=10, research_question_id="q1", depth=2)
    assert cov.state == CoverageState.PENDING

    result = ExaminationResult(covered=True, findings=("f1",))
    assert result.covered is True
