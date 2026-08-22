"""F5.2 command surface, canonical digest, and caller-controlled-field tests."""

from dataclasses import fields, replace

from intelligence.application.actor_context import ActorContext
from intelligence.application.claims import (
    ProposedClaimEvidenceLink,
    RegisterClaim,
    digest_register_claim,
)
from intelligence.claims.models import (
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidenceRole,
    ClaimPredicate,
    TemporalAbsenceReason,
    TextClaimValue,
    UndatedClaimTemporal,
)
from intelligence.domain.identifiers import ClaimCommandId, CorrelationId
from tests.claims.synthetic_fixtures import (
    INVESTIGATION_ID,
    USER_ID,
    WORKSPACE_ID,
    synthetic_history,
)


def _command() -> RegisterClaim:
    evidence = synthetic_history().latest
    return RegisterClaim(
        command_id=ClaimCommandId.new(),
        investigation_id=INVESTIGATION_ID,
        predicate_code=ClaimPredicate.LEGAL_NAME,
        predicate_version=1,
        value=TextClaimValue("Synthetic Alpha Registry Test Ltd."),
        temporal=UndatedClaimTemporal(TemporalAbsenceReason.NOT_PROVIDED),
        criticality=ClaimCriticality.STANDARD,
        creation_method=ClaimCreationMethod.MANUAL,
        creation_method_version=1,
        links=(
            ProposedClaimEvidenceLink(
                evidence.id,
                evidence.evidence_digest,
                ClaimEvidenceRole.SUPPORTS,
            ),
        ),
    )


def test_command_cannot_supply_policy_or_outcome_and_digest_is_deterministic() -> None:
    command = _command()
    names = {item.name for item in fields(command)}
    assert names.isdisjoint(
        {
            "workspace_id",
            "outcome",
            "reason_code",
            "policy_id",
            "policy_version",
            "manifest_id",
            "manifest_version",
            "manifest_digest",
            "decision",
        }
    )
    actor = ActorContext(
        user_id=USER_ID,
        workspace_id=WORKSPACE_ID,
        correlation_id=CorrelationId.new(),
    )
    assert digest_register_claim(actor, command) == digest_register_claim(actor, command)
    changed = replace(command, value=TextClaimValue("Different synthetic value"))
    assert digest_register_claim(actor, changed) != digest_register_claim(actor, command)
    assert "Synthetic Alpha" not in repr(command)
