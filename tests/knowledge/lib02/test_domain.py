import dataclasses
import pytest

from knowledge.lib02 import (
    ContinuityCapsule,
    Coverage,
    CoverageState,
    ExaminationResult,
    Lab,
    NonFinding,
    Program,
    ProgramNext,
    ReopenCondition,
    ReopenConditionError,
    ResearchQuestion,
    Source,
    TrackNext,
    Version,
)


def test_immutable_domain_objects():
    src = Source(name="feed", version="v1")
    ver = Version(value="1.0")
    cap = ContinuityCapsule(
        capsule_id="c1",
        owning_lab=Lab.STRATEGY,
        program_id="p1",
        research_question_id="q1",
        why="why",
        current="current",
        done="done",
        do_not_repeat="dont repeat",
        open_inconclusive="open",
        bounded_unknowns="unknowns",
        issuance_provenance="prov",
        issued_at="now",
    )

    assert cap.routing_snapshots == ()


def test_reopen_condition_enforced():
    rq = ResearchQuestion(
        question_id="q1",
        program_id="p1",
        owning_lab=Lab.STRATEGY,
        question="exact bounded question",
        scope="bounded scope",
        governed_status="ACTIVE",
        status="CLOSED",
    )
    with pytest.raises(ReopenConditionError):
        rq.reopen(None)

    cond = ReopenCondition(reason="new info")
    reopened = rq.reopen(cond)
    assert reopened.status == "OPEN"


def test_coverage_and_examination_separation():
    s = Source(name="s", version="v2")
    v = Version(value="v2")
    cov = Coverage(source=s, version=v, range_start=0, range_end=10, research_question_id="q1", depth=2)
    assert cov.state == CoverageState.PENDING

    result = ExaminationResult(covered=True, findings=("f1",))
    assert result.covered is True
