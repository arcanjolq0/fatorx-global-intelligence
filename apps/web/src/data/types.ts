export type IsoDateTime = string;

export type InvestigationLifecycleStatus =
  | "CREATED"
  | "IDENTIFYING"
  | "WAITING_FOR_ENTITY_CONFIRMATION"
  | "PLANNING"
  | "COLLECTING"
  | "NORMALIZING"
  | "VERIFYING"
  | "ANALYZING"
  | "WAITING_FOR_REVIEW"
  | "COMPLETED"
  | "PARTIALLY_COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type ContextualEligibilityStatus = "ELIGIBLE" | "RESTRICTED" | "REJECTED";

export type EffectiveEvidenceAdmissibilityStatus =
  "PENDING" | "ADMISSIBLE" | "RESTRICTED" | "EXPIRED" | "REVOKED" | "REJECTED";

export type EffectiveFactualReviewStatus =
  "PENDING" | "ACCEPTED" | "REJECTED" | "NEEDS_CORRECTION" | "INVALIDATED";

export interface JurisdictionPresentation {
  readonly code: string;
  readonly label: string;
}

export interface PrimaryIdentifierPresentation {
  readonly label: string;
  readonly value: string;
}

export interface EntityConfirmationPresentation {
  readonly basis: readonly string[];
  readonly confirmedAt: IsoDateTime | null;
  readonly status: "CONFIRMED" | "PENDING_HUMAN_CONFIRMATION";
}

export interface EntitySummary {
  readonly aliases: readonly string[];
  readonly confirmation: EntityConfirmationPresentation;
  readonly id: string;
  readonly identifiers: readonly PrimaryIdentifierPresentation[];
  readonly legalName: string;
  readonly primaryIdentifier: PrimaryIdentifierPresentation;
  readonly jurisdiction: JurisdictionPresentation;
}

export interface EntityCandidate {
  readonly aliases: readonly string[];
  readonly ambiguityNote: string;
  readonly id: string;
  readonly legalName: string;
  readonly primaryIdentifier: PrimaryIdentifierPresentation | null;
  readonly jurisdiction: JurisdictionPresentation;
  readonly matchStrength: "HIGH" | "MEDIUM" | "LOW" | "EXCLUDED";
  readonly requiresHumanReview: boolean;
  readonly matchingSignals: readonly string[];
}

export interface InvestigationSummary {
  readonly id: string;
  readonly entity: EntitySummary;
  readonly lifecycleStatus: InvestigationLifecycleStatus;
  readonly updatedAt: IsoDateTime;
  readonly evidenceCount: number;
  readonly pendingClaimCount: number;
  readonly pendingReviewCount: number;
}

export interface ContextualEligibilityPresentation {
  readonly purpose: "INTERNAL_CLAIM_VERIFICATION";
  readonly status: ContextualEligibilityStatus;
}

export interface GlobalAdmissibilityPresentation {
  readonly purpose: "INTERNAL_FACTUAL_EVIDENCE_USE";
  readonly status: EffectiveEvidenceAdmissibilityStatus;
}

export interface FactualReviewPresentation {
  readonly decisionOutcome:
    | "ACCEPTED_FOR_INTERNAL_FACTUAL_USE"
    | "REJECTED_FOR_INTERNAL_FACTUAL_USE"
    | "NEEDS_CORRECTION"
    | null;
  readonly effectiveStatus: EffectiveFactualReviewStatus;
  readonly purpose: "INTERNAL_FACTUAL_CLAIM_USE";
  readonly reviewedAt: IsoDateTime | null;
}

export interface EvidenceUsePresentation {
  readonly evidenceId: string;
  readonly role: "SUPPORTS" | "CONTRADICTS" | "QUALIFIES";
  readonly eligibility: ContextualEligibilityPresentation;
  readonly admissibility: GlobalAdmissibilityPresentation;
}

export interface EvidenceSummary {
  readonly id: string;
  readonly investigationId: string;
  readonly label: string;
  readonly kind: "TEXT" | "STRUCTURED_DATA" | "IMAGE" | "EXTERNAL_REFERENCE";
  readonly capturedAt: IsoDateTime;
  readonly admissibility: GlobalAdmissibilityPresentation;
}

export interface ClaimSummary {
  readonly id: string;
  readonly investigationId: string;
  readonly label: string;
  readonly assessment: "INSUFFICIENT" | "SUPPORTED" | "CONFLICTED";
  readonly criticality: "STANDARD" | "CRITICAL";
  readonly evidenceUses: readonly EvidenceUsePresentation[];
  readonly factualReview: FactualReviewPresentation;
}

export interface ClaimReviewSummary extends FactualReviewPresentation {
  readonly id: string;
  readonly claimId: string;
  readonly investigationId: string;
}

export interface InvestigationDetail extends InvestigationSummary {
  readonly createdAt: IsoDateTime;
  readonly entityCandidates: readonly EntityCandidate[];
  readonly evidence: readonly EvidenceSummary[];
  readonly claims: readonly ClaimSummary[];
  readonly factualReviews: readonly ClaimReviewSummary[];
}

export interface ActivityItem {
  readonly id: string;
  readonly investigationId: string;
  readonly occurredAt: IsoDateTime;
  readonly summary: string;
  readonly type:
    "INVESTIGATION_CREATED" | "LIFECYCLE_UPDATED" | "EVIDENCE_RECORDED" | "CLAIM_REVIEWED";
}

export interface DashboardSummary {
  readonly asOf: IsoDateTime;
  readonly totalInvestigations: number;
  readonly activeInvestigations: number;
  readonly investigationsAwaitingReview: number;
  readonly evidenceItems: number;
  readonly claims: number;
}
