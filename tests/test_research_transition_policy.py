from research.transition_policy import decide_transition, effective_state


def test_outcome_complete_uses_domain_verdict():
    result = {"terminal_state": "OUTCOME-COMPLETE", "terminal_verdict": "REJECTED"}
    assert effective_state(result) == "REJECTED"


def test_rejected_dispatches_only_to_predeclared_successor():
    job = {
        "transitions": {
            "REJECTED": {"action": "DISPATCH", "object_id": "NEXT-OBJECT"}
        }
    }
    result = {"terminal_state": "OUTCOME-COMPLETE", "terminal_verdict": "REJECTED"}
    decision = decide_transition(job, result)
    assert decision.action == "DISPATCH"
    assert decision.next_object_id == "NEXT-OBJECT"


def test_unclassified_outcome_fails_closed():
    decision = decide_transition({}, {"terminal_state": "OUTCOME-COMPLETE"})
    assert decision.action == "STOP"
    assert decision.effective_state == "OUTCOME-COMPLETE-UNCLASSIFIED"
    assert decision.reason == "ambiguous-terminal"


def test_blocked_tooling_without_allowlisted_transition_stops():
    decision = decide_transition({}, {"terminal_state": "BLOCKED-TOOLING"})
    assert decision.action == "STOP"
    assert decision.reason == "no-predeclared-transition"


def test_promotion_routes_to_governed_paper_manifest_candidate():
    decision = decide_transition(
        {},
        {"terminal_state": "OUTCOME-COMPLETE", "terminal_verdict": "PROMOTION-ELIGIBLE"},
    )
    assert decision.action == "PAPER-MANIFEST-CANDIDATE"
    assert decision.effective_state == "PROMOTION-ELIGIBLE"


def test_invalid_transition_action_fails_closed():
    job = {
        "transitions": {
            "REJECTED": {"action": "RUN_ARBITRARY_CODE", "object_id": "NEXT"}
        }
    }
    result = {"terminal_state": "OUTCOME-COMPLETE", "terminal_verdict": "REJECTED"}
    decision = decide_transition(job, result)
    assert decision.action == "STOP"
    assert decision.reason == "disallowed-transition-action"
