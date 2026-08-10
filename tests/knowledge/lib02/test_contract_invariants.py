import dataclasses

import pytest

from knowledge.lib02 import (
    ActorContext,
    AuthorizationFailure,
    ClearProgramNext,
    ClearTrackNext,
    Claim,
    ContinuityCapsule,
    EvidenceRelation,
    Lab,
    NonFinding,
    Program,
    ProgramNext,
    ReconciliationState,
    ReopenCondition,
    ResearchQuestion,
    Role,
    SetProgramNext,
    SetTrackNext,
    Source,
    TrackNext,
    Version,
    ValidationFailure,
)


def test_program_and_research_question_routing_authority_cannot_be_interchanged():
    program = Program(
        program_id="p1",
        owning_lab=Lab.STRATEGY,
        purpose="bounded purpose",
        scope="bounded scope",
        governed_status="ACTIVE",
    )
    question = ResearchQuestion(
        question_id="q1",
        program_id="p1",
        owning_lab=Lab.STRATEGY,
        question="exact bounded question",
        scope="bounded scope",
        governed_status="ACTIVE",
    )

    with pytest.raises(ValidationFailure):
        SetProgramNext(
            program_id="p1",
            program_next=ProgramNext(program_id="p1", actor_id="a1"),
            reason="route",
        ).validate_target(question)

    with pytest.raises(ValidationFailure):
        SetTrackNext(
            research_question_id="q1",
            track_next=TrackNext(research_question_id="q1", actor_id="a1"),
            reason="route",
        ).validate_target(program)


def test_continuity_capsule_routing_fields_are_snapshot_only():
    capsule = ContinuityCapsule(
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

    assert capsule.program_next_snapshot is None
    assert capsule.track_next_snapshot is None
    assert capsule.routing_snapshots == ()
    assert not hasattr(capsule, "routing_authority")


def test_continuity_capsule_is_immutable_after_issuance():
    capsule = ContinuityCapsule(
        capsule_id="c2",
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

    with pytest.raises(dataclasses.FrozenInstanceError):
        capsule.why = "changed"


def test_nonfinding_requires_bounded_examination_provenance():
    with pytest.raises(ValidationFailure):
        NonFinding(
            non_finding_id="nf1",
            owning_lab=Lab.STRATEGY,
            program_id="p1",
            question_id="q1",
            source=Claim(claim_id="c1", semantic="s", source=None),
            version=None,
            artifact_reference="a1",
            range_start=0,
            range_end=1,
            search_domain="domain",
            examined_question="q1",
            condition="cond",
            examination_method="method",
            depth=1,
            result="none",
            provenance="",
            limitations="none",
            created_at="now",
        )


def test_evidence_relation_append_only_superseding_preserves_original():
    source = Claim(claim_id="c0", semantic="s", source=None)
    original = EvidenceRelation(
        relation_id="r1",
        target_id="t1",
        target_kind="Claim",
        source=source,
        version=None,
        relation_type="supports",
        provenance="prov",
        created_at="now",
    )
    superseding = EvidenceRelation(
        relation_id="r2",
        target_id="t1",
        target_kind="Claim",
        source=source,
        version=None,
        relation_type="supports",
        provenance="prov2",
        supersedes_relation_id="r1",
        created_at="later",
    )

    assert original.relation_id == "r1"
    assert superseding.supersedes_relation_id == original.relation_id


def test_reconciliation_state_contains_only_allowed_values():
    assert set(ReconciliationState.__members__.keys()) == {"CURRENT", "UNRECONCILED", "CONFLICT"}


def test_clearing_program_next_and_track_next_requires_reason():
    with pytest.raises(ValidationFailure):
        ClearProgramNext(program_id="p1", reason="")

    with pytest.raises(ValidationFailure):
        ClearTrackNext(research_question_id="q1", reason="")


def test_closed_research_question_cannot_receive_new_track_next():
    rq = ResearchQuestion(
        question_id="q1",
        program_id="p1",
        owning_lab=Lab.STRATEGY,
        question="exact bounded question",
        scope="bounded scope",
        governed_status="ACTIVE",
        status="CLOSED",
    )

    with pytest.raises(ValidationFailure):
        SetTrackNext(
            research_question_id="q1",
            track_next=TrackNext(research_question_id="q1", actor_id="a1"),
            reason="route",
        ).validate_target(rq)


def test_cross_lab_routing_mutation_fails():
    actor = ActorContext(actor_id="a1", role=Role.STRATEGY_LAB, lab=Lab.STRATEGY)
    program = Program(
        program_id="p1",
        owning_lab=Lab.GLOBAL_INVESTMENT,
        purpose="bounded purpose",
        scope="bounded scope",
        governed_status="ACTIVE",
    )

    with pytest.raises(AuthorizationFailure):
        SetProgramNext(
            program_id="p1",
            program_next=ProgramNext(program_id="p1", actor_id="a1"),
            reason="route",
        ).authorize(actor, program)


def test_missing_routing_fallback_remains_absent():
    program = Program(
        program_id="p1",
        owning_lab=Lab.STRATEGY,
        purpose="bounded purpose",
        scope="bounded scope",
        governed_status="ACTIVE",
    )
    question = ResearchQuestion(
        question_id="q1",
        program_id="p1",
        owning_lab=Lab.STRATEGY,
        question="exact bounded question",
        scope="bounded scope",
        governed_status="ACTIVE",
    )

    assert program.program_next is None
    assert question.track_next is None
