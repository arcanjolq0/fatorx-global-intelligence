import { Badge } from "../ui";
import type {
  ContextualEligibilityStatus,
  EffectiveEvidenceAdmissibilityStatus,
  EffectiveFactualReviewStatus,
  EvidenceRole,
  EvidenceUsePresentation,
} from "../../data/types";
import {
  eligibilityStatusLabels,
  evidenceRoleLabels,
  evidenceStatusLabels,
  factualReviewStatusLabels,
  getEligibilityStatusTone,
  getEvidenceRoleTone,
  getEvidenceStatusTone,
  getReviewStatusTone,
} from "../../presentation/investigationPresentation";

export function EvidenceStatusBadge({
  status,
}: {
  readonly status: EffectiveEvidenceAdmissibilityStatus;
}) {
  return <Badge tone={getEvidenceStatusTone(status)}>{evidenceStatusLabels[status]}</Badge>;
}

export function ContextualEligibilityBadge({
  status,
}: {
  readonly status: ContextualEligibilityStatus;
}) {
  return <Badge tone={getEligibilityStatusTone(status)}>{eligibilityStatusLabels[status]}</Badge>;
}

export function ReviewStatusBadge({ status }: { readonly status: EffectiveFactualReviewStatus }) {
  return <Badge tone={getReviewStatusTone(status)}>{factualReviewStatusLabels[status]}</Badge>;
}

export function EvidenceRoleBadge({ role }: { readonly role: EvidenceRole }) {
  return <Badge tone={getEvidenceRoleTone(role)}>{evidenceRoleLabels[role]}</Badge>;
}

function uniqueValues<Value extends string>(values: readonly Value[]): readonly Value[] {
  return [...new Set(values)];
}

export function SemanticStatusGroup({
  evidenceUses,
  reviewStatus,
}: {
  readonly evidenceUses: readonly EvidenceUsePresentation[];
  readonly reviewStatus: EffectiveFactualReviewStatus;
}) {
  const eligibilityStatuses = uniqueValues(evidenceUses.map((item) => item.eligibility.status));
  const admissibilityStatuses = uniqueValues(evidenceUses.map((item) => item.admissibility.status));

  return (
    <dl className="semantic-status-group">
      <div>
        <dt>F5.2 · Elegibilidade contextual</dt>
        <dd>
          {eligibilityStatuses.map((status) => (
            <ContextualEligibilityBadge key={status} status={status} />
          ))}
        </dd>
      </div>
      <div>
        <dt>F5.3 · Admissibilidade da Evidence</dt>
        <dd>
          {admissibilityStatuses.map((status) => (
            <EvidenceStatusBadge key={status} status={status} />
          ))}
        </dd>
      </div>
      <div>
        <dt>F5.4 · Revisão factual da Claim</dt>
        <dd>
          <ReviewStatusBadge status={reviewStatus} />
        </dd>
      </div>
    </dl>
  );
}

export function ClaimStatusStack({
  evidenceUses,
  reviewStatus,
}: {
  readonly evidenceUses: readonly EvidenceUsePresentation[];
  readonly reviewStatus: EffectiveFactualReviewStatus;
}) {
  return <SemanticStatusGroup evidenceUses={evidenceUses} reviewStatus={reviewStatus} />;
}

export function ContradictionIndicator({
  evidenceUses,
}: {
  readonly evidenceUses: readonly EvidenceUsePresentation[];
}) {
  const counts = { SUPPORTS: 0, CONTRADICTS: 0, QUALIFIES: 0 };
  for (const item of evidenceUses) {
    counts[item.role] += 1;
  }

  return (
    <div aria-label="Papéis das evidências" className="evidence-role-counts">
      <span>
        <strong>{counts.SUPPORTS}</strong> sustenta(m)
      </span>
      <span className={counts.CONTRADICTS > 0 ? "role-count role-count--danger" : "role-count"}>
        <strong>{counts.CONTRADICTS}</strong> contradiz(em)
      </span>
      <span>
        <strong>{counts.QUALIFIES}</strong> qualifica(m)
      </span>
    </div>
  );
}
