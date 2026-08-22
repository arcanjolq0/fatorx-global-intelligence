"""Framework-neutral errors exposed by the application boundary."""


class ApplicationError(Exception):
    """Base class for expected application-layer failures."""


class PersistenceError(ApplicationError):
    """A database operation failed without exposing adapter details."""


class PersistenceConflictError(PersistenceError):
    """A key, foreign-key, or other integrity constraint was rejected."""


class PersistenceDataError(PersistenceError):
    """Persisted values cannot be reconstituted as a valid domain snapshot."""


class PersistenceStateError(PersistenceError):
    """A persistence operation was attempted outside an active transaction."""


class AuthorizationDeniedError(ApplicationError):
    """The authenticated actor cannot perform the requested operation."""

    def __init__(self) -> None:
        super().__init__("Operation is not authorized.")


class ResourceNotFoundError(ApplicationError):
    """A tenant-scoped resource is absent without revealing another tenant."""

    def __init__(self) -> None:
        super().__init__("Requested resource was not found.")


class MembershipConflictError(ApplicationError):
    """A membership operation conflicts with its current state."""

    def __init__(self) -> None:
        super().__init__("Membership operation conflicts with current state.")


class LastOwnerProtectionError(ApplicationError):
    """An operation would remove the final active owner of a workspace."""

    def __init__(self) -> None:
        super().__init__("The workspace must retain an active owner.")


class InvalidOperationError(ApplicationError):
    """A known application operation is invalid in the current state."""

    def __init__(self) -> None:
        super().__init__("Operation is invalid in the current state.")


class InvestigationTransitionError(ApplicationError):
    """A lifecycle command is invalid for the current investigation state."""

    def __init__(self) -> None:
        super().__init__("Investigation transition is invalid.")


class ConcurrentInvestigationUpdateError(ApplicationError):
    """Optimistic locking rejected a stale expected state version."""

    def __init__(self) -> None:
        super().__init__("Investigation state version is stale.")


class InvestigationCommandCollisionError(ApplicationError):
    """A durable command ID was reused for different allowlisted content."""

    def __init__(self) -> None:
        super().__init__("Investigation command identifier conflicts with prior content.")


class CandidateInputDigestMismatchError(ApplicationError):
    """Candidate submission does not target the persisted identification input."""

    def __init__(self) -> None:
        super().__init__("Candidate batch does not match the identification input.")


class CandidateReviewError(ApplicationError):
    """Candidate batch or matching policy cannot be evaluated safely."""

    def __init__(self) -> None:
        super().__init__("Candidate review request is invalid.")


class InactiveCandidateBatchError(ApplicationError):
    """A confirmation command does not target the investigation's active batch."""

    def __init__(self) -> None:
        super().__init__("Candidate batch is not active for this investigation.")


class CandidateNotInBatchError(ApplicationError):
    """The selected candidate is absent from the tenant-scoped active batch."""

    def __init__(self) -> None:
        super().__init__("Selected candidate was not found in the active batch.")


class CandidateExcludedError(ApplicationError):
    """A matching hard conflict makes the selected candidate ineligible."""

    def __init__(self) -> None:
        super().__init__("Excluded candidates cannot be confirmed.")


class EntityConfirmationReasonError(ApplicationError):
    """The closed human-review reason is incompatible with rank/classification."""

    def __init__(self) -> None:
        super().__init__("Entity confirmation reason is incompatible with the candidate.")


class InvalidMaterializationPolicyError(ApplicationError):
    """The requested Company materialization policy is unsupported."""

    def __init__(self) -> None:
        super().__init__("Company materialization policy is invalid.")


class InvalidInvestigationPlanningError(ApplicationError):
    """Persisted inputs or the supplied policy cannot produce a safe plan."""

    def __init__(self) -> None:
        super().__init__("Investigation planning request is invalid.")


class RequiredPlanningCapabilityUnavailableError(ApplicationError):
    """A required policy capability has no statically eligible connector."""

    def __init__(self) -> None:
        super().__init__("A required investigation capability is unavailable.")


class InvestigationPlanningBudgetError(ApplicationError):
    """Known plan cost is incompatible with the persisted budget."""

    def __init__(self) -> None:
        super().__init__("Investigation plan exceeds the available budget.")


class InvestigationPlanningDeadlineError(ApplicationError):
    """The deterministic critical path cannot fit before the deadline."""

    def __init__(self) -> None:
        super().__init__("Investigation plan is incompatible with the deadline.")


class InvestigationPlanAlreadyExistsError(ApplicationError):
    """Another command already created the sole plan for an investigation."""

    def __init__(self) -> None:
        super().__init__("An investigation plan already exists.")


class InvalidCollectionActivationError(ApplicationError):
    """The persisted plan or activation policy cannot produce a safe manifest."""

    def __init__(self) -> None:
        super().__init__("Collection activation request is invalid.")


class CollectionActivationDeadlineError(ApplicationError):
    """The READY-operation critical path no longer fits before the persisted deadline."""

    def __init__(self) -> None:
        super().__init__("Collection activation exceeds the investigation deadline.")


class CollectionRunAlreadyExistsError(ApplicationError):
    """Another command already activated collection for this investigation or plan."""

    def __init__(self) -> None:
        super().__init__("A collection run already exists.")


class InvalidCollectionExecutionError(ApplicationError):
    """The manifest, connector, runtime, or command cannot be executed safely."""

    def __init__(self) -> None:
        super().__init__("Collection operation execution request is invalid.")


class CollectionExecutionAlreadyOwnedError(ApplicationError):
    """Another command durably owns this manifest operation."""

    def __init__(self) -> None:
        super().__init__("Collection operation execution is already owned.")


class CollectionExecutionInProgressError(ApplicationError):
    """The same command has durable ownership but no completion yet."""

    def __init__(self) -> None:
        super().__init__("Collection operation execution is still in progress.")


class CollectionExecutionDependencyError(ApplicationError):
    """A manifest dependency lacks a usable durable completion."""

    def __init__(self) -> None:
        super().__init__("Collection operation dependencies are not complete.")


class InvalidEvidenceContextError(ApplicationError):
    """Evidence does not match the persisted investigation and entity decision."""

    def __init__(self) -> None:
        super().__init__("Evidence context is invalid.")


class EvidenceCommandCollisionError(ApplicationError):
    """A tenant-scoped evidence command ID was reused with different content."""

    def __init__(self) -> None:
        super().__init__("Evidence command identifier conflicts with prior content.")


class EvidenceVersionConflictError(ApplicationError):
    """A correction or revocation targeted a stale evidence version."""

    def __init__(self) -> None:
        super().__init__("Evidence version is stale.")


class EvidenceAlreadyRevokedError(ApplicationError):
    """A revoked evidence history cannot receive more lifecycle changes."""

    def __init__(self) -> None:
        super().__init__("Evidence history is already revoked.")


class InvalidClaimContextError(ApplicationError):
    """Claim does not match the investigation, entity decision, or lifecycle."""

    def __init__(self) -> None:
        super().__init__("Claim context is invalid.")


class ClaimCommandCollisionError(ApplicationError):
    """A tenant-scoped Claim command ID was reused with different content."""

    def __init__(self) -> None:
        super().__init__("Claim command identifier conflicts with prior content.")


class ClaimVersionConflictError(ApplicationError):
    """A Claim correction targeted a stale version or changed its predicate."""

    def __init__(self) -> None:
        super().__init__("Claim version or predicate is stale.")


class InvalidClaimEvidenceError(ApplicationError):
    """A proposed Evidence link cannot be validated safely."""

    def __init__(self) -> None:
        super().__init__("Claim Evidence link is invalid.")


__all__ = [
    "ApplicationError",
    "AuthorizationDeniedError",
    "CandidateExcludedError",
    "CandidateInputDigestMismatchError",
    "CandidateNotInBatchError",
    "CandidateReviewError",
    "ClaimCommandCollisionError",
    "ClaimVersionConflictError",
    "CollectionActivationDeadlineError",
    "CollectionExecutionAlreadyOwnedError",
    "CollectionExecutionDependencyError",
    "CollectionExecutionInProgressError",
    "CollectionRunAlreadyExistsError",
    "ConcurrentInvestigationUpdateError",
    "EntityConfirmationReasonError",
    "EvidenceAlreadyRevokedError",
    "EvidenceCommandCollisionError",
    "EvidenceVersionConflictError",
    "InactiveCandidateBatchError",
    "InvalidClaimContextError",
    "InvalidClaimEvidenceError",
    "InvalidCollectionActivationError",
    "InvalidCollectionExecutionError",
    "InvalidEvidenceContextError",
    "InvalidInvestigationPlanningError",
    "InvalidMaterializationPolicyError",
    "InvalidOperationError",
    "InvestigationCommandCollisionError",
    "InvestigationPlanAlreadyExistsError",
    "InvestigationPlanningBudgetError",
    "InvestigationPlanningDeadlineError",
    "InvestigationTransitionError",
    "LastOwnerProtectionError",
    "MembershipConflictError",
    "PersistenceConflictError",
    "PersistenceDataError",
    "PersistenceError",
    "PersistenceStateError",
    "RequiredPlanningCapabilityUnavailableError",
    "ResourceNotFoundError",
]
