"""
MarketHunter

Tests for CORE-GAP-07 Manual Review - Slice 1
(manual_review/foundation.py).
"""

from __future__ import annotations

import dataclasses
import unittest

from audit_read_model.foundation import AuditProjectionReference, AuditSourceReference
from manual_review.foundation import (
    ReviewActionClass,
    ReviewActionReference,
    ReviewActionRequest,
    ReviewActorEvidence,
    ReviewActorReference,
    ReviewAuthorizationAssessment,
    ReviewAuthorizationAuthorityReference,
    ReviewAuthorizationReason,
    ReviewAuthorizationStatus,
    ReviewCapabilityGrant,
    ReviewCapabilityReference,
    ReviewCapabilityRequirement,
    ReviewEvidenceDisposition,
    ReviewTargetBinding,
    ReviewTargetDisposition,
    ReviewTargetReference,
    assess_review_authorization,
)


def make_actor(**overrides) -> ReviewActorReference:
    kwargs = dict(actor_kind="human", actor_id="actor-1", revision_or_version=None)
    kwargs.update(overrides)
    return ReviewActorReference(**kwargs)


def make_authority(**overrides) -> ReviewAuthorizationAuthorityReference:
    kwargs = dict(
        authority_kind="governance_council",
        authority_id="authority-1",
        revision_or_version=None,
    )
    kwargs.update(overrides)
    return ReviewAuthorizationAuthorityReference(**kwargs)


def make_capability(**overrides) -> ReviewCapabilityReference:
    kwargs = dict(capability_id="cap-inspect", revision_or_version=None)
    kwargs.update(overrides)
    return ReviewCapabilityReference(**kwargs)


def make_capability_requirement(**overrides) -> ReviewCapabilityRequirement:
    kwargs = dict(capability=make_capability(), issuing_authority=make_authority())
    kwargs.update(overrides)
    return ReviewCapabilityRequirement(**kwargs)


def make_source_reference(**overrides) -> AuditSourceReference:
    kwargs = dict(
        source_domain="risk",
        source_type="RiskResultRecord",
        source_id="risk-1",
        revision_or_version="1",
    )
    kwargs.update(overrides)
    return AuditSourceReference(**kwargs)


def make_projection_reference(**overrides) -> AuditProjectionReference:
    kwargs = dict(projection_id="proj-1", revision=1)
    kwargs.update(overrides)
    return AuditProjectionReference(**kwargs)


def make_target_reference(**overrides) -> ReviewTargetReference:
    kwargs = dict(source_reference=make_source_reference(), projection_reference=None)
    kwargs.update(overrides)
    return ReviewTargetReference(**kwargs)


def make_action_reference(**overrides) -> ReviewActionReference:
    kwargs = dict(review_id="review-1", revision=1)
    kwargs.update(overrides)
    return ReviewActionReference(**kwargs)


def make_request(**overrides) -> ReviewActionRequest:
    kwargs = dict(
        reference=make_action_reference(),
        actor=make_actor(),
        target=make_target_reference(),
        action_class=ReviewActionClass.INSPECT,
        required_capability=make_capability_requirement(),
        require_current_target=False,
        supersedes_review_revision=None,
    )
    kwargs.update(overrides)
    return ReviewActionRequest(**kwargs)


class EnumValueTests(unittest.TestCase):
    def test_evidence_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in ReviewEvidenceDisposition},
            {"KNOWN", "UNKNOWN", "UNAVAILABLE", "CONFLICT"},
        )

    def test_action_class_values(self) -> None:
        self.assertEqual(
            {m.value for m in ReviewActionClass},
            {"INSPECT", "ACKNOWLEDGE", "COMMENT", "ESCALATE", "REQUEST_CHANGE"},
        )

    def test_target_disposition_values(self) -> None:
        self.assertEqual(
            {m.value for m in ReviewTargetDisposition},
            {
                "CURRENT",
                "UNKNOWN",
                "UNAVAILABLE",
                "STALE",
                "CONFLICT",
                "SUPERSEDED",
                "SOURCE_CHANGED",
            },
        )

    def test_status_values(self) -> None:
        self.assertEqual(
            {m.value for m in ReviewAuthorizationStatus},
            {"AUTHORIZED", "NOT_AUTHORIZED"},
        )

    def test_reason_values(self) -> None:
        self.assertEqual(
            {m.value for m in ReviewAuthorizationReason},
            {
                "ACTOR_UNRESOLVED",
                "ACTOR_AMBIGUOUS",
                "ACTOR_EVIDENCE_NOT_USABLE",
                "GRANT_UNRESOLVED",
                "GRANT_AMBIGUOUS",
                "GRANT_EVIDENCE_NOT_USABLE",
                "TARGET_UNRESOLVED",
                "TARGET_AMBIGUOUS",
                "TARGET_DISPOSITION_NOT_USABLE",
                "TARGET_CURRENT_REQUIRED",
            },
        )


class ReviewActorReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        actor = make_actor()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            actor.actor_id = "other"  # type: ignore[misc]

    def test_blank_actor_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_actor(actor_id="  ")

    def test_wrong_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_actor(actor_id=123)  # type: ignore[arg-type]

    def test_optional_revision_none_accepted(self) -> None:
        actor = make_actor(revision_or_version=None)
        self.assertIsNone(actor.revision_or_version)

    def test_blank_optional_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_actor(revision_or_version="  ")


class ReviewAuthorizationAuthorityReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        authority = make_authority()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            authority.authority_id = "other"  # type: ignore[misc]

    def test_blank_authority_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_authority(authority_kind="")


class ReviewCapabilityReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        capability = make_capability()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            capability.capability_id = "other"  # type: ignore[misc]

    def test_blank_capability_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_capability(capability_id="")


class ReviewActorEvidenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        evidence = ReviewActorEvidence(make_actor(), ReviewEvidenceDisposition.KNOWN)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            evidence.disposition = ReviewEvidenceDisposition.UNKNOWN  # type: ignore[misc]

    def test_wrong_actor_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewActorEvidence("not-an-actor", ReviewEvidenceDisposition.KNOWN)  # type: ignore[arg-type]

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewActorEvidence(make_actor(), "KNOWN")  # type: ignore[arg-type]


class ReviewCapabilityRequirementTests(unittest.TestCase):
    def test_frozen(self) -> None:
        requirement = make_capability_requirement()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            requirement.capability = make_capability()  # type: ignore[misc]

    def test_wrong_capability_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewCapabilityRequirement("not-a-capability", make_authority())  # type: ignore[arg-type]

    def test_wrong_authority_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewCapabilityRequirement(make_capability(), "not-an-authority")  # type: ignore[arg-type]


class ReviewCapabilityGrantTests(unittest.TestCase):
    def test_frozen(self) -> None:
        grant = ReviewCapabilityGrant(
            make_actor(),
            make_capability(),
            make_authority(),
            ReviewEvidenceDisposition.KNOWN,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            grant.disposition = ReviewEvidenceDisposition.UNKNOWN  # type: ignore[misc]

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewCapabilityGrant(
                make_actor(), make_capability(), make_authority(), "KNOWN"  # type: ignore[arg-type]
            )


class ReviewActionReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        reference = make_action_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reference.revision = 2  # type: ignore[misc]

    def test_blank_review_id_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_action_reference(review_id=" ")

    def test_zero_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_action_reference(revision=0)

    def test_bool_revision_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_action_reference(revision=True)  # type: ignore[arg-type]


class ReviewTargetReferenceTests(unittest.TestCase):
    def test_frozen(self) -> None:
        target = make_target_reference()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            target.source_reference = None  # type: ignore[misc]

    def test_source_only_accepted(self) -> None:
        target = ReviewTargetReference(
            source_reference=make_source_reference(), projection_reference=None
        )
        self.assertIsNotNone(target.source_reference)
        self.assertIsNone(target.projection_reference)

    def test_projection_only_accepted(self) -> None:
        target = ReviewTargetReference(
            source_reference=None, projection_reference=make_projection_reference()
        )
        self.assertIsNone(target.source_reference)
        self.assertIsNotNone(target.projection_reference)

    def test_both_none_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ReviewTargetReference(source_reference=None, projection_reference=None)

    def test_both_supplied_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ReviewTargetReference(
                source_reference=make_source_reference(),
                projection_reference=make_projection_reference(),
            )

    def test_wrong_source_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewTargetReference(
                source_reference="not-a-source-reference",  # type: ignore[arg-type]
                projection_reference=None,
            )

    def test_wrong_projection_reference_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewTargetReference(
                source_reference=None,
                projection_reference="not-a-projection-reference",  # type: ignore[arg-type]
            )


class ReviewTargetBindingTests(unittest.TestCase):
    def test_frozen(self) -> None:
        binding = ReviewTargetBinding(
            make_target_reference(), ReviewTargetDisposition.CURRENT
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            binding.disposition = ReviewTargetDisposition.STALE  # type: ignore[misc]

    def test_wrong_disposition_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ReviewTargetBinding(make_target_reference(), "CURRENT")  # type: ignore[arg-type]


class ReviewActionRequestTests(unittest.TestCase):
    def test_frozen(self) -> None:
        request = make_request()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            request.require_current_target = True  # type: ignore[misc]

    def test_wrong_action_class_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_request(action_class="INSPECT")  # type: ignore[arg-type]

    def test_wrong_require_current_target_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_request(require_current_target="yes")  # type: ignore[arg-type]

    def test_supersedes_none_accepted(self) -> None:
        request = make_request(supersedes_review_revision=None)
        self.assertIsNone(request.supersedes_review_revision)

    def test_supersedes_strictly_less_than_revision_accepted(self) -> None:
        request = make_request(
            reference=make_action_reference(revision=3),
            supersedes_review_revision=2,
        )
        self.assertEqual(request.supersedes_review_revision, 2)

    def test_supersedes_equal_to_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_request(
                reference=make_action_reference(revision=2),
                supersedes_review_revision=2,
            )

    def test_supersedes_greater_than_revision_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_request(
                reference=make_action_reference(revision=2),
                supersedes_review_revision=3,
            )

    def test_supersedes_zero_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_request(
                reference=make_action_reference(revision=2),
                supersedes_review_revision=0,
            )

    def test_supersedes_bool_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_request(
                reference=make_action_reference(revision=2),
                supersedes_review_revision=True,  # type: ignore[arg-type]
            )

    def test_no_predecessor_lookup_field_exists(self) -> None:
        # supersedes_review_revision is a caller-supplied int, never a
        # lookup key or object reference - confirming the field type
        # is exactly int, not a reference type that could be resolved.
        request = make_request(
            reference=make_action_reference(revision=3),
            supersedes_review_revision=1,
        )
        self.assertIsInstance(request.supersedes_review_revision, int)


class ReviewAuthorizationAssessmentTests(unittest.TestCase):
    def test_not_authorized_requires_at_least_one_reason(self) -> None:
        with self.assertRaises(ValueError):
            ReviewAuthorizationAssessment(
                status=ReviewAuthorizationStatus.NOT_AUTHORIZED, reasons=()
            )

    def test_authorized_forbids_reasons(self) -> None:
        with self.assertRaises(ValueError):
            ReviewAuthorizationAssessment(
                status=ReviewAuthorizationStatus.AUTHORIZED,
                reasons=(ReviewAuthorizationReason.ACTOR_UNRESOLVED,),
            )

    def test_frozen(self) -> None:
        assessment = ReviewAuthorizationAssessment(
            status=ReviewAuthorizationStatus.AUTHORIZED, reasons=()
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            assessment.status = ReviewAuthorizationStatus.NOT_AUTHORIZED  # type: ignore[misc]


class AssessReviewAuthorizationTests(unittest.TestCase):
    def _usable_bindings(
        self, actor=None, capability_requirement=None, target=None
    ):
        actor = actor or make_actor()
        capability_requirement = capability_requirement or make_capability_requirement()
        target = target or make_target_reference()
        actor_evidence = (
            ReviewActorEvidence(actor, ReviewEvidenceDisposition.KNOWN),
        )
        grants = (
            ReviewCapabilityGrant(
                actor,
                capability_requirement.capability,
                capability_requirement.issuing_authority,
                ReviewEvidenceDisposition.KNOWN,
            ),
        )
        target_bindings = (
            ReviewTargetBinding(target, ReviewTargetDisposition.CURRENT),
        )
        return actor_evidence, grants, target_bindings

    def test_wrong_request_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_review_authorization("not-a-request", (), (), ())  # type: ignore[arg-type]

    def test_wrong_actor_evidence_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_review_authorization(make_request(), [], (), ())  # type: ignore[arg-type]

    def test_wrong_grants_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_review_authorization(make_request(), (), [], ())  # type: ignore[arg-type]

    def test_wrong_target_bindings_type_rejected(self) -> None:
        with self.assertRaises(TypeError):
            assess_review_authorization(make_request(), (), (), [])  # type: ignore[arg-type]

    def test_fully_resolved_current_target_is_authorized(self) -> None:
        request = make_request()
        actor_evidence, grants, target_bindings = self._usable_bindings()

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.AUTHORIZED)
        self.assertEqual(result.reasons, ())

    def test_actor_unresolved_fails_closed(self) -> None:
        request = make_request()
        _, grants, target_bindings = self._usable_bindings()

        result = assess_review_authorization(request, (), grants, target_bindings)
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.ACTOR_UNRESOLVED, result.reasons)

    def test_actor_ambiguous_fails_closed(self) -> None:
        request = make_request()
        actor = request.actor
        actor_evidence = (
            ReviewActorEvidence(actor, ReviewEvidenceDisposition.KNOWN),
            ReviewActorEvidence(actor, ReviewEvidenceDisposition.CONFLICT),
        )
        _, grants, target_bindings = self._usable_bindings()

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.ACTOR_AMBIGUOUS, result.reasons)

    def test_all_non_known_actor_dispositions_fail_closed(self) -> None:
        for disposition in (
            ReviewEvidenceDisposition.UNKNOWN,
            ReviewEvidenceDisposition.UNAVAILABLE,
            ReviewEvidenceDisposition.CONFLICT,
        ):
            with self.subTest(disposition=disposition):
                request = make_request()
                actor_evidence = (
                    ReviewActorEvidence(request.actor, disposition),
                )
                _, grants, target_bindings = self._usable_bindings()

                result = assess_review_authorization(
                    request, actor_evidence, grants, target_bindings
                )
                self.assertEqual(
                    result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED
                )
                self.assertIn(
                    ReviewAuthorizationReason.ACTOR_EVIDENCE_NOT_USABLE,
                    result.reasons,
                )

    def test_wrong_actor_never_matches(self) -> None:
        request = make_request()
        other_actor = make_actor(actor_id="someone-else")
        actor_evidence = (
            ReviewActorEvidence(other_actor, ReviewEvidenceDisposition.KNOWN),
        )
        _, grants, target_bindings = self._usable_bindings()

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.ACTOR_UNRESOLVED, result.reasons)

    def test_grant_unresolved_fails_closed(self) -> None:
        request = make_request()
        actor_evidence, _, target_bindings = self._usable_bindings()

        result = assess_review_authorization(
            request, actor_evidence, (), target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.GRANT_UNRESOLVED, result.reasons)

    def test_grant_ambiguous_fails_closed(self) -> None:
        request = make_request()
        actor_evidence, _, target_bindings = self._usable_bindings()
        grants = (
            ReviewCapabilityGrant(
                request.actor,
                request.required_capability.capability,
                request.required_capability.issuing_authority,
                ReviewEvidenceDisposition.KNOWN,
            ),
            ReviewCapabilityGrant(
                request.actor,
                request.required_capability.capability,
                request.required_capability.issuing_authority,
                ReviewEvidenceDisposition.CONFLICT,
            ),
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.GRANT_AMBIGUOUS, result.reasons)

    def test_all_non_known_grant_dispositions_fail_closed(self) -> None:
        for disposition in (
            ReviewEvidenceDisposition.UNKNOWN,
            ReviewEvidenceDisposition.UNAVAILABLE,
            ReviewEvidenceDisposition.CONFLICT,
        ):
            with self.subTest(disposition=disposition):
                request = make_request()
                actor_evidence, _, target_bindings = self._usable_bindings()
                grants = (
                    ReviewCapabilityGrant(
                        request.actor,
                        request.required_capability.capability,
                        request.required_capability.issuing_authority,
                        disposition,
                    ),
                )

                result = assess_review_authorization(
                    request, actor_evidence, grants, target_bindings
                )
                self.assertEqual(
                    result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED
                )
                self.assertIn(
                    ReviewAuthorizationReason.GRANT_EVIDENCE_NOT_USABLE,
                    result.reasons,
                )

    def test_wrong_capability_never_matches_grant(self) -> None:
        request = make_request()
        actor_evidence, _, target_bindings = self._usable_bindings()
        grants = (
            ReviewCapabilityGrant(
                request.actor,
                make_capability(capability_id="cap-other"),
                request.required_capability.issuing_authority,
                ReviewEvidenceDisposition.KNOWN,
            ),
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.GRANT_UNRESOLVED, result.reasons)

    def test_wrong_issuing_authority_never_matches_grant(self) -> None:
        request = make_request()
        actor_evidence, _, target_bindings = self._usable_bindings()
        grants = (
            ReviewCapabilityGrant(
                request.actor,
                request.required_capability.capability,
                make_authority(authority_id="authority-other"),
                ReviewEvidenceDisposition.KNOWN,
            ),
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.GRANT_UNRESOLVED, result.reasons)

    def test_target_unresolved_fails_closed(self) -> None:
        request = make_request()
        actor_evidence, grants, _ = self._usable_bindings()

        result = assess_review_authorization(
            request, actor_evidence, grants, ()
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.TARGET_UNRESOLVED, result.reasons)

    def test_target_ambiguous_fails_closed(self) -> None:
        request = make_request()
        actor_evidence, grants, _ = self._usable_bindings()
        target_bindings = (
            ReviewTargetBinding(request.target, ReviewTargetDisposition.CURRENT),
            ReviewTargetBinding(request.target, ReviewTargetDisposition.STALE),
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(ReviewAuthorizationReason.TARGET_AMBIGUOUS, result.reasons)

    def test_target_current_always_usable(self) -> None:
        request = make_request(require_current_target=True)
        actor_evidence, grants, target_bindings = self._usable_bindings(
            target=request.target
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.AUTHORIZED)

    def test_target_superseded_usable_when_current_not_required(self) -> None:
        request = make_request(require_current_target=False)
        actor_evidence, grants, _ = self._usable_bindings(target=request.target)
        target_bindings = (
            ReviewTargetBinding(
                request.target, ReviewTargetDisposition.SUPERSEDED
            ),
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.AUTHORIZED)

    def test_target_superseded_fails_when_current_required(self) -> None:
        request = make_request(require_current_target=True)
        actor_evidence, grants, _ = self._usable_bindings(target=request.target)
        target_bindings = (
            ReviewTargetBinding(
                request.target, ReviewTargetDisposition.SUPERSEDED
            ),
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertIn(
            ReviewAuthorizationReason.TARGET_CURRENT_REQUIRED, result.reasons
        )

    def test_all_other_target_dispositions_fail_closed(self) -> None:
        for disposition in (
            ReviewTargetDisposition.UNKNOWN,
            ReviewTargetDisposition.UNAVAILABLE,
            ReviewTargetDisposition.STALE,
            ReviewTargetDisposition.CONFLICT,
            ReviewTargetDisposition.SOURCE_CHANGED,
        ):
            with self.subTest(disposition=disposition):
                request = make_request()
                actor_evidence, grants, _ = self._usable_bindings(
                    target=request.target
                )
                target_bindings = (
                    ReviewTargetBinding(request.target, disposition),
                )

                result = assess_review_authorization(
                    request, actor_evidence, grants, target_bindings
                )
                self.assertEqual(
                    result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED
                )
                self.assertIn(
                    ReviewAuthorizationReason.TARGET_DISPOSITION_NOT_USABLE,
                    result.reasons,
                )

    def test_target_with_projection_reference_resolves(self) -> None:
        target = ReviewTargetReference(
            source_reference=None, projection_reference=make_projection_reference()
        )
        request = make_request(target=target)
        actor_evidence, grants, target_bindings = self._usable_bindings(
            target=target
        )

        result = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(result.status, ReviewAuthorizationStatus.AUTHORIZED)

    def test_reasons_collected_across_all_categories_not_short_circuited(
        self,
    ) -> None:
        request = make_request()

        result = assess_review_authorization(request, (), (), ())
        self.assertEqual(result.status, ReviewAuthorizationStatus.NOT_AUTHORIZED)
        self.assertEqual(
            result.reasons,
            (
                ReviewAuthorizationReason.ACTOR_UNRESOLVED,
                ReviewAuthorizationReason.GRANT_UNRESOLVED,
                ReviewAuthorizationReason.TARGET_UNRESOLVED,
            ),
        )

    def test_deterministic_replay(self) -> None:
        request = make_request()
        actor_evidence, grants, target_bindings = self._usable_bindings()

        first = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        second = assess_review_authorization(
            request, actor_evidence, grants, target_bindings
        )
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.reasons, second.reasons)

    def test_does_not_mutate_inputs(self) -> None:
        request = make_request()
        actor_evidence, grants, target_bindings = self._usable_bindings()
        request_before = dataclasses.astuple(request)

        assess_review_authorization(request, actor_evidence, grants, target_bindings)

        self.assertEqual(request_before, dataclasses.astuple(request))

    def test_no_action_execution_all_action_classes_treated_uniformly(self) -> None:
        for action_class in ReviewActionClass:
            with self.subTest(action_class=action_class):
                request = make_request(action_class=action_class)
                actor_evidence, grants, target_bindings = self._usable_bindings()

                result = assess_review_authorization(
                    request, actor_evidence, grants, target_bindings
                )
                self.assertEqual(
                    result.status, ReviewAuthorizationStatus.AUTHORIZED
                )


class ScopeDisciplineTests(unittest.TestCase):
    def _module_tree(self):
        import ast
        from pathlib import Path

        import manual_review.foundation as module

        return ast.parse(Path(module.__file__).read_text(encoding="utf-8"))

    def _imported_names(self) -> set[str]:
        import ast

        imported: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.add(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name)
        return imported

    def _referenced_names(self) -> set[str]:
        import ast

        tree = self._module_tree()
        return {
            node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
        } | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }

    def test_module_is_stdlib_only_plus_audit_read_model(self) -> None:
        imported = self._imported_names()
        allowed_prefixes = (
            "__future__",
            "dataclasses",
            "enum",
            "audit_read_model",
        )
        for name in imported:
            self.assertTrue(
                any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in allowed_prefixes
                ),
                f"unexpected import: {name}",
            )

    def test_audit_read_model_import_is_the_named_narrow_set_only(self) -> None:
        import ast

        imported_from_audit: set[str] = set()
        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "audit_read_model.foundation"
            ):
                for alias in node.names:
                    imported_from_audit.add(alias.name)

        self.assertEqual(
            imported_from_audit,
            {"AuditProjectionReference", "AuditSourceReference"},
        )

    def test_no_other_source_domain_imports(self) -> None:
        imported = self._imported_names()
        for forbidden in (
            "strategies",
            "risk",
            "portfolio",
            "portfolio_v1",
            "models",
            "research",
            "execution",
            "explainability",
            "time_semantics",
            "api",
            "dashboard",
        ):
            self.assertNotIn(forbidden, imported)
            for name in imported:
                self.assertFalse(
                    name.startswith(forbidden + "."),
                    f"unexpected cross-domain import: {name}",
                )

    def test_no_source_domain_object_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "StrategyIdentity",
            "RiskSizingProposal",
            "RiskResultRecord",
            "PortfolioDecision",
            "ExplanationRecord",
            "ResearchTrade",
            "ExecutionOrder",
            "TemporalFact",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_research_trade_notional_reference(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("notional", referenced)

    def test_no_action_execution_vocabulary(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "approve",
            "reject",
            "resize",
            "cancel",
            "execute",
            "override",
            "write_back",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_iam_rbac_user_directory_or_workflow_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "Role",
            "Permission",
            "RBAC",
            "ABAC",
            "UserDirectory",
            "Workflow",
            "Notification",
            "EscalationRoute",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_wall_clock_random_db_filesystem_or_network_usage(self) -> None:
        referenced = self._referenced_names()
        self.assertNotIn("now", referenced)
        self.assertNotIn("utcnow", referenced)
        self.assertNotIn("uuid4", referenced)

        imported = self._imported_names()
        for forbidden in (
            "sqlite3",
            "os",
            "pathlib",
            "subprocess",
            "requests",
            "fastapi",
            "httpx",
            "socket",
            "ntplib",
            "datetime",
            "random",
        ):
            self.assertNotIn(forbidden, imported)

    def test_no_persistence_api_ui_reports_references(self) -> None:
        referenced = self._referenced_names()
        for forbidden in (
            "APIRouter",
            "FastAPI",
            "Report",
            "Dashboard",
            "Repository",
            "Session",
        ):
            self.assertNotIn(forbidden, referenced)

    def test_no_sort_or_min_max_selector_calls(self) -> None:
        import ast

        for node in ast.walk(self._module_tree()):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("sorted", "min", "max")
            ):
                self.fail(f"unexpected {node.func.id}() call in module")

    def test_no_latest_or_current_selector_exported(self) -> None:
        import manual_review.foundation as module

        for forbidden in ("latest", "current", "get_current", "get_latest"):
            self.assertFalse(hasattr(module, forbidden))


if __name__ == "__main__":
    unittest.main()
