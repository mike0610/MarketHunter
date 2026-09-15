from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


DOMAIN_VERDICTS = {
    "REJECTED",
    "BLOCKED-EVIDENCE",
    "CANDIDATE",
    "PROMOTION-ELIGIBLE",
    "NEEDS-BOUNDED-FIX",
}

EXECUTION_TERMINALS = {
    "OUTCOME-COMPLETE",
    "BLOCKED-EVIDENCE",
    "BLOCKED-TOOLING",
    "EXECUTION-TIMEOUT",
    "PROVIDER-BLOCKED",
}

ALLOWED_ACTIONS = {"STOP", "DISPATCH", "PAPER-MANIFEST-CANDIDATE"}


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    action: str
    effective_state: str
    next_object_id: str | None = None
    reason: str | None = None


def _domain_verdict(result: Mapping[str, Any]) -> str | None:
    for key in ("terminal_verdict", "verdict"):
        value = result.get(key)
        if isinstance(value, str) and value in DOMAIN_VERDICTS:
            return value
    return None


def effective_state(result: Mapping[str, Any]) -> str:
    terminal = result.get("terminal_state")
    if not isinstance(terminal, str) or terminal not in EXECUTION_TERMINALS:
        return "UNKNOWN"

    if terminal == "OUTCOME-COMPLETE":
        return _domain_verdict(result) or "OUTCOME-COMPLETE-UNCLASSIFIED"

    return terminal


def decide_transition(
    job: Mapping[str, Any],
    result: Mapping[str, Any],
) -> TransitionDecision:
    state = effective_state(result)

    if state in {"UNKNOWN", "OUTCOME-COMPLETE-UNCLASSIFIED"}:
        return TransitionDecision(
            action="STOP",
            effective_state=state,
            reason="ambiguous-terminal",
        )

    transitions = job.get("transitions")
    if transitions is None:
        transitions = {}
    if not isinstance(transitions, Mapping):
        return TransitionDecision(
            action="STOP",
            effective_state=state,
            reason="invalid-transition-map",
        )

    raw = transitions.get(state)
    if raw is None:
        if state == "PROMOTION-ELIGIBLE":
            return TransitionDecision(
                action="PAPER-MANIFEST-CANDIDATE",
                effective_state=state,
                reason="promotion-requires-governed-admission",
            )
        return TransitionDecision(
            action="STOP",
            effective_state=state,
            reason="no-predeclared-transition",
        )

    if not isinstance(raw, Mapping):
        return TransitionDecision(
            action="STOP",
            effective_state=state,
            reason="invalid-transition-entry",
        )

    action = raw.get("action")
    if action not in ALLOWED_ACTIONS:
        return TransitionDecision(
            action="STOP",
            effective_state=state,
            reason="disallowed-transition-action",
        )

    if action == "DISPATCH":
        object_id = raw.get("object_id")
        if not isinstance(object_id, str) or not object_id:
            return TransitionDecision(
                action="STOP",
                effective_state=state,
                reason="missing-next-object",
            )
        return TransitionDecision(
            action="DISPATCH",
            effective_state=state,
            next_object_id=object_id,
        )

    return TransitionDecision(
        action=action,
        effective_state=state,
        reason=raw.get("reason") if isinstance(raw.get("reason"), str) else None,
    )
