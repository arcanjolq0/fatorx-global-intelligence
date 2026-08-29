"""F5.4 factual Claim-review functional tests."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.claim_evidence_policy import (
    ClaimEvidenceEligibilityPolicyV1,
    ControlledEvidenceAnchorV1,
    build_manifest,
    locator_digest,
)
from intelligence.application.claim_review import DecideClaimReview
from intelligence.application.claims import CorrectClaim, ProposedClaimEvidenceLink
from intelligence.application.errors import (
    ClaimReviewCommandCollisionError,
    ClaimReviewPredecessorError,
    InvalidClaimReviewError,
    ResourceNotFoundError,
)
from intelligence.application.evidence_admissibility import (
    DecideEvidenceAdmissibility,
    EvidenceAdmissibilityOperationResult,
)
from intelligence.application.evidence_admissibility_policy import (
    ControlledTestEvidenceAnchorV1,
    EvidenceAdmissibilityPolicyV1,
)
from intelligence.application.evidence_admissibility_policy import (
    build_manifest as build_admissibility_manifest,
)
from intelligence.application.evidence_admissibility_policy import (
    locator_digest as admissibility_locator_digest,
)
from intelligence.application.services.claim_review import ClaimReviewService
from intelligence.application.services.claims import ClaimService
from intelligence.application.services.evidence import EvidenceService
from intelligence.application.services.evidence_admissibility import EvidenceAdmissibilityService
from intelligence.claims.errors import ClaimHistoryError
from intelligence.claims.models import (
    Claim,
    ClaimCorrectionReason,
    ClaimEvidenceRole,
    ClaimEvidenceUseOutcome,
    ClaimHistory,
    TextClaimValue,
)
from intelligence.claims.review import (
    ClaimReviewDecision,
    ClaimReviewHistory,
    ClaimReviewReason,
    ClaimReviewRequestedAction,
    EffectiveClaimReviewStatus,
    claim_review_basis_digest,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    ClaimCommandId,
    ClaimId,
    ClaimReviewCommandId,
    EvidenceAdmissibilityCommandId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.evidence.admissibility import (
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
)
from tests.unit.application.fakes import FakeClock, FakeUnitOfWorkFactory
from tests.unit.application.test_claim_service import _register
from tests.unit.application.test_claim_service import _setup as claim_setup
from tests.unit.application.test_entity_confirmation import _later_investigation
from tests.unit.application.test_evidence_admissibility_service import _second_owner
from tests.unit.application.test_evidence_service import NOW
from tests.unit.application.test_evidence_service import _register_command as register_evidence

type ClaimReviewSetup = tuple[
    ActorContext,
    ActorContext,
    FakeUnitOfWorkFactory,
    ClaimReviewService,
    Claim,
    EvidenceAdmissibilityOperationResult,
]
type ClaimReviewRolesSetup = tuple[
    ActorContext,
    ActorContext,
    FakeUnitOfWorkFactory,
    ClaimReviewService,
    Claim,
    tuple[EvidenceAdmissibilityOperationResult, ...],
]


def _setup() -> ClaimReviewSetup:
    creator, database, _, _ = claim_setup()
    evidence = next(iter(database.evidence_histories.values())).latest
    artifact = next(iter(database.evidence_histories.values())).artifact
    claim_policy = ClaimEvidenceEligibilityPolicyV1(
        build_manifest(
            (
                ControlledEvidenceAnchorV1(
                    artifact_original_sha256=artifact.original_content_sha256,
                    evidence_content_sha256=evidence.content_sha256,
                    evidence_kind=evidence.kind,
                    locator_type=evidence.locator.type,
                    locator_digest=locator_digest(evidence.locator),
                ),
            )
        )
    )
    factory = FakeUnitOfWorkFactory(database)
    claims = ClaimService(factory, ContextualAuthorizer(), FakeClock(NOW), claim_policy)
    claim = claims.register(creator, _register(database)).history.latest
    reviewer = _second_owner(creator, database)
    admissibility_policy = EvidenceAdmissibilityPolicyV1(
        build_admissibility_manifest(
            (
                ControlledTestEvidenceAnchorV1(
                    artifact_original_sha256=artifact.original_content_sha256,
                    evidence_content_sha256=evidence.content_sha256,
                    evidence_kind=evidence.kind,
                    locator_type=evidence.locator.type,
                    locator_digest=admissibility_locator_digest(evidence.locator),
                ),
            )
        )
    )
    admissibility = EvidenceAdmissibilityService(
        factory, ContextualAuthorizer(), FakeClock(NOW), admissibility_policy
    )
    admitted = admissibility.decide(
        reviewer,
        DecideEvidenceAdmissibility(
            command_id=EvidenceAdmissibilityCommandId.new(),
            investigation_id=evidence.investigation_id,
            evidence_id=evidence.id,
            expected_evidence_digest=evidence.evidence_digest,
            expected_previous_decision_digest=None,
            requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
            reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
            requested_valid_until=None,
        ),
    )
    reviews = ClaimReviewService(factory, ContextualAuthorizer(), FakeClock(NOW))
    return creator, reviewer, factory, reviews, claim, admitted


def _setup_with_roles(
    roles: tuple[ClaimEvidenceRole, ...],
) -> ClaimReviewRolesSetup:
    creator, database, _, _ = claim_setup()
    factory = FakeUnitOfWorkFactory(database)
    investigation = next(iter(database.investigations.values()))
    database.investigations[(creator.workspace_id, investigation.id)] = _later_investigation(
        investigation,
        state=InvestigationState.COLLECTING,
        state_version=investigation.state_version + 1,
    )
    evidence_service = EvidenceService(factory, ContextualAuthorizer(), FakeClock(NOW))
    while len(database.evidence_histories) < len(roles):
        index = len(database.evidence_histories)
        located = f"Evidence {index}".encode()
        evidence_service.register(
            creator,
            register_evidence(database, located_content=located, content_original=located.decode()),
        )
    collecting = database.investigations[(creator.workspace_id, investigation.id)]
    database.investigations[(creator.workspace_id, investigation.id)] = _later_investigation(
        collecting,
        state=InvestigationState.VERIFYING,
        state_version=collecting.state_version + 1,
    )
    histories = tuple(database.evidence_histories.values())
    evidence_records = tuple(history.latest for history in histories)
    claim_policy = ClaimEvidenceEligibilityPolicyV1(
        build_manifest(
            tuple(
                ControlledEvidenceAnchorV1(
                    artifact_original_sha256=history.artifact.original_content_sha256,
                    evidence_content_sha256=evidence.content_sha256,
                    evidence_kind=evidence.kind,
                    locator_type=evidence.locator.type,
                    locator_digest=locator_digest(evidence.locator),
                )
                for history, evidence in zip(histories, evidence_records, strict=True)
            )
        )
    )
    claims = ClaimService(factory, ContextualAuthorizer(), FakeClock(NOW), claim_policy)
    claim = claims.register(
        creator,
        replace(
            _register(database),
            links=tuple(
                ProposedClaimEvidenceLink(evidence.id, evidence.evidence_digest, role)
                for evidence, role in zip(evidence_records, roles, strict=True)
            ),
        ),
    ).history.latest
    reviewer = _second_owner(creator, database)
    admissibility = EvidenceAdmissibilityService(
        factory,
        ContextualAuthorizer(),
        FakeClock(NOW),
        EvidenceAdmissibilityPolicyV1(
            build_admissibility_manifest(
                tuple(
                    ControlledTestEvidenceAnchorV1(
                        artifact_original_sha256=history.artifact.original_content_sha256,
                        evidence_content_sha256=evidence.content_sha256,
                        evidence_kind=evidence.kind,
                        locator_type=evidence.locator.type,
                        locator_digest=admissibility_locator_digest(evidence.locator),
                    )
                    for history, evidence in zip(histories, evidence_records, strict=True)
                )
            )
        ),
    )
    admitted = tuple(
        admissibility.decide(
            reviewer,
            DecideEvidenceAdmissibility(
                command_id=EvidenceAdmissibilityCommandId.new(),
                investigation_id=evidence.investigation_id,
                evidence_id=evidence.id,
                expected_evidence_digest=evidence.evidence_digest,
                expected_previous_decision_digest=None,
                requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
                reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
                requested_valid_until=None,
            ),
        )
        for evidence in evidence_records
    )
    return (
        creator,
        reviewer,
        factory,
        ClaimReviewService(factory, ContextualAuthorizer(), FakeClock(NOW)),
        claim,
        admitted,
    )


def _admissibility_service(
    factory: FakeUnitOfWorkFactory, *, at: datetime
) -> EvidenceAdmissibilityService:
    histories = tuple(factory.database.evidence_histories.values())
    return EvidenceAdmissibilityService(
        factory,
        ContextualAuthorizer(),
        FakeClock(at),
        EvidenceAdmissibilityPolicyV1(
            build_admissibility_manifest(
                tuple(
                    ControlledTestEvidenceAnchorV1(
                        artifact_original_sha256=history.artifact.original_content_sha256,
                        evidence_content_sha256=history.latest.content_sha256,
                        evidence_kind=history.latest.kind,
                        locator_type=history.latest.locator.type,
                        locator_digest=admissibility_locator_digest(history.latest.locator),
                    )
                    for history in histories
                )
            )
        ),
    )


def _command(
    claim: Claim,
    *,
    command_id: ClaimReviewCommandId | None = None,
    claim_id: ClaimId | None = None,
    expected_previous_decision_digest: str | None = None,
    requested_action: ClaimReviewRequestedAction = ClaimReviewRequestedAction.ACCEPT,
    reason_code: ClaimReviewReason = ClaimReviewReason.FACTUAL_BASIS_ACCEPTED,
) -> DecideClaimReview:
    return DecideClaimReview(
        command_id=command_id or ClaimReviewCommandId.new(),
        investigation_id=claim.investigation_id,
        claim_id=claim_id or claim.id,
        expected_claim_digest=claim.claim_digest,
        expected_previous_decision_digest=expected_previous_decision_digest,
        requested_action=requested_action,
        reason_code=reason_code,
    )


def test_accept_requires_both_f52_eligible_and_f53_admissible() -> None:
    _creator, reviewer, factory, reviews, claim, _ = _setup()
    accepted = reviews.decide(reviewer, _command(claim))
    assert accepted.effective.status is EffectiveClaimReviewStatus.ACCEPTED
    assert accepted.history.latest.outcome.value == "ACCEPTED_FOR_INTERNAL_FACTUAL_USE"
    assert factory.created[-1].claim_reviews.add_initial_calls

    _creator, reviewer, factory, reviews, claim, _ = _setup()
    history = next(iter(factory.database.claim_histories.values()))
    link = history.links[0]
    object.__setattr__(link.use_decision, "outcome", ClaimEvidenceUseOutcome.RESTRICTED)
    with pytest.raises(InvalidClaimReviewError):
        reviews.decide(reviewer, _command(claim))


def test_negative_reviews_need_no_positive_gate_and_creator_cannot_accept() -> None:
    creator, _reviewer, _, reviews, claim, _ = _setup()
    with pytest.raises(InvalidClaimReviewError):
        reviews.decide(creator, _command(claim))
    rejected = reviews.decide(
        creator,
        _command(
            claim,
            requested_action=ClaimReviewRequestedAction.REJECT,
            reason_code=ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED,
        ),
    )
    assert rejected.effective.status is EffectiveClaimReviewStatus.REJECTED


def test_replay_collision_and_tamper_fail_closed() -> None:
    _, reviewer, _, reviews, claim, _ = _setup()
    command = _command(claim)
    accepted = reviews.decide(reviewer, command)
    assert reviews.decide(reviewer, command).replayed
    with pytest.raises(ClaimReviewCommandCollisionError):
        reviews.decide(
            reviewer,
            _command(
                claim,
                command_id=command.command_id,
                requested_action=ClaimReviewRequestedAction.REJECT,
                reason_code=ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED,
            ),
        )
    object.__setattr__(accepted.history.latest, "review_basis_digest", "0" * 64)
    with pytest.raises(InvalidClaimReviewError):
        reviews.read(reviewer, claim.id, as_of=NOW)


def test_supersession_and_nonexistent_or_preclaim_reads_fail_safely() -> None:
    _, reviewer, _, reviews, claim, _ = _setup()
    first = reviews.decide(reviewer, _command(claim))
    second = reviews.decide(
        reviewer,
        _command(
            claim,
            expected_previous_decision_digest=first.history.latest.decision_digest,
            requested_action=ClaimReviewRequestedAction.RETURN_FOR_CORRECTION,
            reason_code=ClaimReviewReason.CLAIM_CORRECTION_REQUIRED,
        ),
    )
    assert len(second.history.decisions) == 2
    assert second.effective.status is EffectiveClaimReviewStatus.NEEDS_CORRECTION
    assert reviews.read(reviewer, claim.id, as_of=NOW).effective.status is (
        EffectiveClaimReviewStatus.NEEDS_CORRECTION
    )
    with pytest.raises(ResourceNotFoundError):
        reviews.read(reviewer, ClaimId.new(), as_of=NOW)
    with pytest.raises(InvalidClaimReviewError):
        reviews.read(reviewer, claim.id, as_of=NOW - timedelta(seconds=1))


def test_positive_review_invalidates_monotonically_and_correction_is_pending() -> None:
    creator, reviewer, factory, reviews, claim, admitted = _setup()
    accepted = reviews.decide(reviewer, _command(claim))
    later = NOW + timedelta(seconds=1)
    evidence_history = next(iter(factory.database.evidence_histories.values()))
    evidence = evidence_history.latest
    restriction = EvidenceAdmissibilityService(
        factory,
        ContextualAuthorizer(),
        FakeClock(later),
        EvidenceAdmissibilityPolicyV1(
            build_admissibility_manifest(
                (
                    ControlledTestEvidenceAnchorV1(
                        artifact_original_sha256=evidence_history.artifact.original_content_sha256,
                        evidence_content_sha256=evidence.content_sha256,
                        evidence_kind=evidence.kind,
                        locator_type=evidence.locator.type,
                        locator_digest=admissibility_locator_digest(evidence.locator),
                    ),
                )
            )
        ),
    )
    restriction.decide(
        reviewer,
        DecideEvidenceAdmissibility(
            command_id=EvidenceAdmissibilityCommandId.new(),
            investigation_id=evidence.investigation_id,
            evidence_id=evidence.id,
            expected_evidence_digest=evidence.evidence_digest,
            expected_previous_decision_digest=admitted.history.latest.decision_digest,
            requested_action=EvidenceAdmissibilityRequestedAction.RESTRICT,
            reason_code=EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED,
            requested_valid_until=None,
        ),
    )
    assert (
        reviews.read(reviewer, claim.id, as_of=NOW).effective.status
        is EffectiveClaimReviewStatus.ACCEPTED
    )
    assert (
        reviews.read(reviewer, claim.id, as_of=later).effective.status
        is EffectiveClaimReviewStatus.INVALIDATED
    )

    claim_policy = ClaimEvidenceEligibilityPolicyV1(
        build_manifest(
            (
                ControlledEvidenceAnchorV1(
                    artifact_original_sha256=evidence_history.artifact.original_content_sha256,
                    evidence_content_sha256=evidence.content_sha256,
                    evidence_kind=evidence.kind,
                    locator_type=evidence.locator.type,
                    locator_digest=locator_digest(evidence.locator),
                ),
            )
        )
    )
    claims = ClaimService(
        factory,
        ContextualAuthorizer(),
        FakeClock(later),
        claim_policy,
    )
    corrected = claims.correct(
        creator,
        CorrectClaim(
            command_id=ClaimCommandId.new(),
            claim_id=claim.id,
            expected_claim_digest=claim.claim_digest,
            predicate_code=claim.predicate_code,
            predicate_version=claim.predicate_version,
            value=TextClaimValue("Corrected value"),
            temporal=claim.temporal,
            criticality=claim.criticality,
            creation_method=claim.creation_method,
            creation_method_version=claim.creation_method_version,
            correction_reason=ClaimCorrectionReason.VALUE_CORRECTION,
            links=(
                ProposedClaimEvidenceLink(
                    evidence.id,
                    evidence.evidence_digest,
                    ClaimEvidenceRole.SUPPORTS,
                ),
            ),
        ),
    )
    assert (
        reviews.read(reviewer, corrected.history.latest.id, as_of=later).effective.status
        is EffectiveClaimReviewStatus.PENDING
    )
    assert accepted.history.latest.claim_id != corrected.history.latest.id


def test_multiple_supports_are_preserved_in_the_complete_basis() -> None:
    _, reviewer, factory, reviews, claim, _ = _setup_with_roles(
        (ClaimEvidenceRole.SUPPORTS, ClaimEvidenceRole.SUPPORTS)
    )
    accepted = reviews.decide(reviewer, _command(claim))
    with factory() as unit_of_work:
        history = unit_of_work.claims.get_history(reviewer.workspace_id, claim.id)
        assert history is not None
        basis = reviews._basis(
            unit_of_work,
            reviewer,
            claim,
            reviews._links_for(history, claim),
            NOW,
        )
    assert accepted.effective.status is EffectiveClaimReviewStatus.ACCEPTED
    assert len(basis) == 2
    assert accepted.history.latest.review_basis_digest == claim_review_basis_digest(
        claim=claim, entries=tuple(reversed(basis))
    )


def test_valid_contradiction_blocks_accept_and_qualifies_is_informational() -> None:
    creator, reviewer, _, reviews, claim, _ = _setup_with_roles(
        (ClaimEvidenceRole.SUPPORTS, ClaimEvidenceRole.CONTRADICTS)
    )
    with pytest.raises(InvalidClaimReviewError):
        reviews.decide(reviewer, _command(claim))
    rejected = reviews.decide(
        creator,
        _command(
            claim,
            requested_action=ClaimReviewRequestedAction.REJECT,
            reason_code=ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED,
        ),
    )
    assert rejected.effective.status is EffectiveClaimReviewStatus.REJECTED

    _, reviewer, _, reviews, qualified, _ = _setup_with_roles(
        (ClaimEvidenceRole.SUPPORTS, ClaimEvidenceRole.QUALIFIES)
    )
    accepted = reviews.decide(reviewer, _command(qualified))
    assert (
        reviews.read(reviewer, qualified.id, as_of=NOW).effective.status
        is EffectiveClaimReviewStatus.ACCEPTED
    )
    assert accepted.history.latest.review_basis_digest


def test_re_admission_does_not_reactivate_and_unlinked_evidence_is_inert() -> None:
    _, reviewer, factory, reviews, claim, admitted = _setup_with_roles(
        (ClaimEvidenceRole.SUPPORTS, ClaimEvidenceRole.SUPPORTS)
    )
    history_key, history = next(iter(factory.database.claim_histories.items()))
    factory.database.claim_histories[history_key] = ClaimHistory(
        versions=history.versions,
        links=(history.links[0],),
    )
    accepted = reviews.decide(reviewer, _command(claim))
    evidence_histories = tuple(factory.database.evidence_histories.values())
    linked = next(
        evidence_history.latest
        for evidence_history in evidence_histories
        if evidence_history.latest.id == history.links[0].evidence_id
    )
    unlinked = next(
        evidence_history.latest
        for evidence_history in evidence_histories
        if evidence_history.latest.id != linked.id
    )
    restricted_at = NOW + timedelta(seconds=1)
    restriction = _admissibility_service(factory, at=restricted_at).decide(
        reviewer,
        DecideEvidenceAdmissibility(
            command_id=EvidenceAdmissibilityCommandId.new(),
            investigation_id=unlinked.investigation_id,
            evidence_id=unlinked.id,
            expected_evidence_digest=unlinked.evidence_digest,
            expected_previous_decision_digest=next(
                result.history.latest.decision_digest
                for result in admitted
                if result.history.latest.evidence_id == unlinked.id
            ),
            requested_action=EvidenceAdmissibilityRequestedAction.RESTRICT,
            reason_code=EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED,
            requested_valid_until=None,
        ),
    )
    assert (
        reviews.read(reviewer, claim.id, as_of=restricted_at).effective.status
        is EffectiveClaimReviewStatus.ACCEPTED
    )
    restriction = _admissibility_service(factory, at=restricted_at).decide(
        reviewer,
        DecideEvidenceAdmissibility(
            command_id=EvidenceAdmissibilityCommandId.new(),
            investigation_id=linked.investigation_id,
            evidence_id=linked.id,
            expected_evidence_digest=linked.evidence_digest,
            expected_previous_decision_digest=next(
                result.history.latest.decision_digest
                for result in admitted
                if result.history.latest.evidence_id == linked.id
            ),
            requested_action=EvidenceAdmissibilityRequestedAction.RESTRICT,
            reason_code=EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED,
            requested_valid_until=None,
        ),
    )
    readmitted_at = restricted_at + timedelta(seconds=1)
    _admissibility_service(factory, at=readmitted_at).decide(
        reviewer,
        DecideEvidenceAdmissibility(
            command_id=EvidenceAdmissibilityCommandId.new(),
            investigation_id=linked.investigation_id,
            evidence_id=linked.id,
            expected_evidence_digest=linked.evidence_digest,
            expected_previous_decision_digest=restriction.history.latest.decision_digest,
            requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
            reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
            requested_valid_until=None,
        ),
    )
    assert accepted.effective.status is EffectiveClaimReviewStatus.ACCEPTED
    assert (
        reviews.read(reviewer, claim.id, as_of=readmitted_at).effective.status
        is EffectiveClaimReviewStatus.INVALIDATED
    )


def test_review_boundary_history_and_basis_invariants_fail_closed() -> None:
    _, reviewer, _, reviews, claim, _ = _setup()
    accepted = reviews.decide(reviewer, _command(claim)).history.latest
    with pytest.raises(TypeError):
        reviews.decide(reviewer, cast(DecideClaimReview, object()))
    with pytest.raises(ResourceNotFoundError):
        reviews.decide(reviewer, _command(claim, claim_id=ClaimId.new()))
    with pytest.raises(ClaimReviewPredecessorError):
        reviews.decide(
            reviewer,
            _command(claim, expected_previous_decision_digest="0" * 64),
        )
    with pytest.raises(ClaimHistoryError):
        ClaimReviewHistory(decisions=())
    with reviews._unit_of_work_factory() as unit_of_work:
        history = unit_of_work.claims.get_history(reviewer.workspace_id, claim.id)
        assert history is not None
        basis = reviews._basis(
            unit_of_work,
            reviewer,
            claim,
            reviews._links_for(history, claim),
            NOW,
        )
    with pytest.raises(ClaimHistoryError):
        claim_review_basis_digest(claim=claim, entries=(basis[0], basis[0]))
    assert "ClaimReviewDecision" in repr(accepted)


def test_domain_decision_and_history_invariants_are_closed() -> None:
    _, reviewer, _, reviews, claim, _ = _setup()
    first = reviews.decide(reviewer, _command(claim)).history.latest
    invalid_builders: tuple[Callable[[], ClaimReviewDecision], ...] = (
        lambda: replace(first, claim_version=0),
        lambda: replace(first, decision_sequence=2, supersedes_decision_id=None),
        lambda: replace(first, policy_id="not-valid"),
        lambda: replace(first, reason_code=ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED),
    )
    for build_invalid in invalid_builders:
        with pytest.raises(InvariantViolationError):
            build_invalid()

    second = reviews.decide(
        reviewer,
        _command(
            claim,
            expected_previous_decision_digest=first.decision_digest,
            requested_action=ClaimReviewRequestedAction.REJECT,
            reason_code=ClaimReviewReason.INTERNAL_FACTUAL_USE_REJECTED,
        ),
    ).history.latest
    object.__setattr__(second, "policy_id", "OTHER_POLICY")
    with pytest.raises(ClaimHistoryError):
        ClaimReviewHistory(decisions=(first, second))


def test_service_missing_dependencies_context_and_replay_history_fail_closed() -> None:
    _, reviewer, factory, reviews, claim, _ = _setup()
    with pytest.raises(TypeError):
        reviews.read(reviewer, cast(ClaimId, object()), as_of=NOW)
    investigation = next(iter(factory.database.investigations.values()))
    investigation_key = (reviewer.workspace_id, investigation.id)
    factory.database.investigations[investigation_key] = _later_investigation(
        investigation,
        state=InvestigationState.COLLECTING,
        state_version=investigation.state_version + 1,
    )
    with pytest.raises(InvalidClaimReviewError):
        reviews.decide(reviewer, _command(claim))
    factory.database.investigations[investigation_key] = investigation

    with factory() as unit_of_work:
        history = unit_of_work.claims.get_history(reviewer.workspace_id, claim.id)
        assert history is not None
        unit_of_work._working_database.evidence_histories.clear()
        with pytest.raises(InvalidClaimReviewError):
            reviews._basis(
                unit_of_work,
                reviewer,
                claim,
                reviews._links_for(history, claim),
                NOW,
            )

    command = _command(claim)
    reviews.decide(reviewer, command)
    factory.database.claim_histories.clear()
    with pytest.raises(InvalidClaimReviewError):
        reviews.decide(reviewer, command)
