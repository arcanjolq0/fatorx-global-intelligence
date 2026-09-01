import type {
  ActivityItem,
  ClaimReviewSummary,
  ClaimSummary,
  DashboardSummary,
  EntityCandidate,
  EntitySummary,
  EvidenceSummary,
  InvestigationDetail,
  InvestigationSummary,
} from "../types";

export interface FixtureDataSet {
  readonly dashboard: DashboardSummary;
  readonly investigations: readonly InvestigationSummary[];
  readonly investigationDetails: readonly InvestigationDetail[];
  readonly evidence: readonly EvidenceSummary[];
  readonly claims: readonly ClaimSummary[];
  readonly factualReviews: readonly ClaimReviewSummary[];
  readonly recentActivity: readonly ActivityItem[];
}

const entities = {
  atlasMeridian: {
    aliases: ["Atlas Meridian Comércio"],
    confirmation: {
      basis: ["Identificador sintético", "Nome legal", "Jurisdição"],
      confirmedAt: "2026-08-27T12:18:00Z",
      status: "CONFIRMED",
    },
    id: "entity-atlas-meridian",
    identifiers: [
      { label: "Registro sintético", value: "BR-FX-000184" },
      { label: "Domínio sintético", value: "atlas-meridian.example" },
    ],
    legalName: "Atlas Meridian Comércio S.A.",
    primaryIdentifier: { label: "Registro sintético", value: "BR-FX-000184" },
    jurisdiction: { code: "BR", label: "Brasil" },
  },
  northstar: {
    aliases: ["Northstar Components"],
    confirmation: {
      basis: ["Identificador sintético", "Nome legal", "Jurisdição"],
      confirmedAt: "2026-08-28T12:24:00Z",
      status: "CONFIRMED",
    },
    id: "entity-northstar-components",
    identifiers: [{ label: "Registro sintético", value: "GB-FX-004271" }],
    legalName: "Northstar Components Ltd.",
    primaryIdentifier: { label: "Registro sintético", value: "GB-FX-004271" },
    jurisdiction: { code: "GB", label: "Reino Unido" },
  },
  rheinbruck: {
    aliases: ["Rheinbruck Maschinen"],
    confirmation: {
      basis: ["Identificador sintético", "Jurisdição"],
      confirmedAt: "2026-08-28T12:32:00Z",
      status: "CONFIRMED",
    },
    id: "entity-rheinbruck-machines",
    identifiers: [{ label: "Registro sintético", value: "DE-FX-003580" }],
    legalName: "Rheinbruck Maschinen GmbH",
    primaryIdentifier: { label: "Registro sintético", value: "DE-FX-003580" },
    jurisdiction: { code: "DE", label: "Alemanha" },
  },
  solandia: {
    aliases: ["Solandia Exportaciones"],
    confirmation: {
      basis: ["Identificador sintético", "Nome legal", "Jurisdição"],
      confirmedAt: "2026-08-30T09:18:00Z",
      status: "CONFIRMED",
    },
    id: "entity-solandia-exports",
    identifiers: [{ label: "Registro sintético", value: "ES-FX-002906" }],
    legalName: "Solandia Exportaciones S.L.",
    primaryIdentifier: { label: "Registro sintético", value: "ES-FX-002906" },
    jurisdiction: { code: "ES", label: "Espanha" },
  },
  pacifica: {
    aliases: ["Pacifica Renewables"],
    confirmation: {
      basis: ["Identificador sintético", "Nome legal", "Jurisdição"],
      confirmedAt: "2026-08-28T12:42:00Z",
      status: "CONFIRMED",
    },
    id: "entity-pacifica-renewables",
    identifiers: [{ label: "Registro sintético", value: "SG-FX-001728" }],
    legalName: "Pacifica Renewables Pte. Ltd.",
    primaryIdentifier: { label: "Registro sintético", value: "SG-FX-001728" },
    jurisdiction: { code: "SG", label: "Singapura" },
  },
} as const satisfies Readonly<Record<string, EntitySummary>>;

const investigations = [
  {
    id: "inv-atlas-meridian",
    entity: entities.atlasMeridian,
    lifecycleStatus: "WAITING_FOR_REVIEW",
    updatedAt: "2026-08-31T14:35:00Z",
    evidenceCount: 4,
    pendingClaimCount: 1,
    pendingReviewCount: 1,
  },
  {
    id: "inv-northstar-components",
    entity: entities.northstar,
    lifecycleStatus: "VERIFYING",
    updatedAt: "2026-08-31T11:20:00Z",
    evidenceCount: 3,
    pendingClaimCount: 2,
    pendingReviewCount: 1,
  },
  {
    id: "inv-rheinbruck-machines",
    entity: entities.rheinbruck,
    lifecycleStatus: "COLLECTING",
    updatedAt: "2026-08-30T16:45:00Z",
    evidenceCount: 1,
    pendingClaimCount: 0,
    pendingReviewCount: 0,
  },
  {
    id: "inv-solandia-exports",
    entity: entities.solandia,
    lifecycleStatus: "PLANNING",
    updatedAt: "2026-08-30T09:10:00Z",
    evidenceCount: 0,
    pendingClaimCount: 0,
    pendingReviewCount: 0,
  },
  {
    id: "inv-pacifica-renewables",
    entity: entities.pacifica,
    lifecycleStatus: "PLANNING",
    updatedAt: "2026-08-29T18:05:00Z",
    evidenceCount: 0,
    pendingClaimCount: 0,
    pendingReviewCount: 0,
  },
] as const satisfies readonly InvestigationSummary[];

const evidence = [
  {
    id: "ev-atlas-registration",
    investigationId: "inv-atlas-meridian",
    label: "Extrato sintético de registro empresarial",
    kind: "STRUCTURED_DATA",
    capturedAt: "2026-08-28T10:00:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "ADMISSIBLE",
    },
  },
  {
    id: "ev-atlas-address",
    investigationId: "inv-atlas-meridian",
    label: "Referência sintética de endereço operacional",
    kind: "TEXT",
    capturedAt: "2026-08-28T10:05:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "PENDING",
    },
  },
  {
    id: "ev-atlas-filing",
    investigationId: "inv-atlas-meridian",
    label: "Documento societário sintético",
    kind: "TEXT",
    capturedAt: "2026-08-28T10:10:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "RESTRICTED",
    },
  },
  {
    id: "ev-atlas-prior-registration",
    investigationId: "inv-atlas-meridian",
    label: "Versão sintética anterior do registro",
    kind: "STRUCTURED_DATA",
    capturedAt: "2026-08-27T09:40:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "REVOKED",
    },
  },
  {
    id: "ev-northstar-registration",
    investigationId: "inv-northstar-components",
    label: "Extrato sintético de registro empresarial",
    kind: "STRUCTURED_DATA",
    capturedAt: "2026-08-29T13:30:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "ADMISSIBLE",
    },
  },
  {
    id: "ev-northstar-alias",
    investigationId: "inv-northstar-components",
    label: "Referência sintética de denominação anterior",
    kind: "EXTERNAL_REFERENCE",
    capturedAt: "2026-08-29T13:35:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "REJECTED",
    },
  },
  {
    id: "ev-northstar-status",
    investigationId: "inv-northstar-components",
    label: "Registro sintético de situação cadastral",
    kind: "TEXT",
    capturedAt: "2026-08-29T13:40:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "EXPIRED",
    },
  },
  {
    id: "ev-rheinbruck-registration",
    investigationId: "inv-rheinbruck-machines",
    label: "Resultado sintético de coleta controlada",
    kind: "STRUCTURED_DATA",
    capturedAt: "2026-08-30T16:30:00Z",
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "PENDING",
    },
  },
] as const satisfies readonly EvidenceSummary[];

const claims = [
  {
    id: "claim-atlas-legal-name",
    investigationId: "inv-atlas-meridian",
    label: "Denominação registrada corresponde a Atlas Meridian Comércio S.A.",
    assessment: "SUPPORTED",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-atlas-registration",
        role: "SUPPORTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "ELIGIBLE" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "ADMISSIBLE",
        },
      },
    ],
    factualReview: {
      purpose: "INTERNAL_FACTUAL_CLAIM_USE",
      decisionOutcome: "ACCEPTED_FOR_INTERNAL_FACTUAL_USE",
      effectiveStatus: "ACCEPTED",
      reviewedAt: "2026-08-30T15:00:00Z",
    },
  },
  {
    id: "claim-atlas-prior-identifier",
    investigationId: "inv-atlas-meridian",
    label: "Identificador anterior permanece aplicável à entidade",
    assessment: "SUPPORTED",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-atlas-prior-registration",
        role: "SUPPORTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "ELIGIBLE" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "REVOKED",
        },
      },
    ],
    factualReview: {
      purpose: "INTERNAL_FACTUAL_CLAIM_USE",
      decisionOutcome: "ACCEPTED_FOR_INTERNAL_FACTUAL_USE",
      effectiveStatus: "INVALIDATED",
      reviewedAt: "2026-08-29T17:20:00Z",
    },
  },
  {
    id: "claim-northstar-registration",
    investigationId: "inv-northstar-components",
    label: "Identificador sintético corresponde ao registro apresentado",
    assessment: "SUPPORTED",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-northstar-registration",
        role: "SUPPORTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "ELIGIBLE" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "ADMISSIBLE",
        },
      },
    ],
    factualReview: {
      purpose: "INTERNAL_FACTUAL_CLAIM_USE",
      decisionOutcome: null,
      effectiveStatus: "PENDING",
      reviewedAt: null,
    },
  },
  {
    id: "claim-northstar-alias",
    investigationId: "inv-northstar-components",
    label: "Denominação anterior pode ser usada como nome vigente",
    assessment: "INSUFFICIENT",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-northstar-alias",
        role: "SUPPORTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "RESTRICTED" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "REJECTED",
        },
      },
    ],
    factualReview: {
      purpose: "INTERNAL_FACTUAL_CLAIM_USE",
      decisionOutcome: "REJECTED_FOR_INTERNAL_FACTUAL_USE",
      effectiveStatus: "REJECTED",
      reviewedAt: "2026-08-31T10:45:00Z",
    },
  },
  {
    id: "claim-northstar-registration-status",
    investigationId: "inv-northstar-components",
    label: "Situação cadastral permanece ativa no período observado",
    assessment: "CONFLICTED",
    criticality: "CRITICAL",
    evidenceUses: [
      {
        evidenceId: "ev-northstar-registration",
        role: "SUPPORTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "ELIGIBLE" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "ADMISSIBLE",
        },
      },
      {
        evidenceId: "ev-northstar-status",
        role: "CONTRADICTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "ELIGIBLE" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "EXPIRED",
        },
      },
    ],
    factualReview: {
      purpose: "INTERNAL_FACTUAL_CLAIM_USE",
      decisionOutcome: "NEEDS_CORRECTION",
      effectiveStatus: "NEEDS_CORRECTION",
      reviewedAt: "2026-08-31T11:00:00Z",
    },
  },
] as const satisfies readonly ClaimSummary[];

const factualReviews = claims.map((claim, index) => ({
  id: `review-${String(index + 1).padStart(2, "0")}`,
  claimId: claim.id,
  investigationId: claim.investigationId,
  ...claim.factualReview,
})) satisfies readonly ClaimReviewSummary[];

const entityCandidatesByInvestigation: Readonly<Record<string, readonly EntityCandidate[]>> = {
  "inv-atlas-meridian": [
    {
      aliases: ["Atlas Meridian Comércio", "Atlas Meridian"],
      ambiguityNote: "Os identificadores coincidem; a confirmação humana ainda é necessária.",
      id: "candidate-atlas-01",
      legalName: "Atlas Meridian Comércio S.A.",
      primaryIdentifier: { label: "Registro sintético", value: "BR-FX-000184" },
      jurisdiction: { code: "BR", label: "Brasil" },
      matchStrength: "HIGH",
      requiresHumanReview: true,
      matchingSignals: ["Identificador coincidente", "Jurisdição coincidente"],
    },
  ],
  "inv-solandia-exports": [
    {
      aliases: ["Solandia Exportaciones", "Solandia Exports"],
      ambiguityNote:
        "O nome e o identificador são compatíveis, mas a seleção deve ser confirmada por uma pessoa.",
      id: "candidate-solandia-01",
      legalName: "Solandia Exportaciones S.L.",
      primaryIdentifier: { label: "Registro sintético", value: "ES-FX-002906" },
      jurisdiction: { code: "ES", label: "Espanha" },
      matchStrength: "HIGH",
      requiresHumanReview: true,
      matchingSignals: ["Nome coincidente", "Identificador fornecido"],
    },
    {
      aliases: ["Solandia Export Services"],
      ambiguityNote:
        "Há semelhança de nome, porém falta um identificador primário para diferenciar a entidade.",
      id: "candidate-solandia-02",
      legalName: "Solandia Export Services S.L.",
      primaryIdentifier: null,
      jurisdiction: { code: "ES", label: "Espanha" },
      matchStrength: "EXCLUDED",
      requiresHumanReview: true,
      matchingSignals: ["Nome semelhante", "Identificador ausente"],
    },
  ],
};

export const entitySearchCandidates = [
  ...(entityCandidatesByInvestigation["inv-atlas-meridian"] ?? []),
  ...(entityCandidatesByInvestigation["inv-solandia-exports"] ?? []),
] as const satisfies readonly EntityCandidate[];

const investigationDetails = investigations.map((investigation) => ({
  ...investigation,
  createdAt:
    investigation.id === "inv-atlas-meridian" ? "2026-08-27T12:00:00Z" : "2026-08-28T12:00:00Z",
  entityCandidates: entityCandidatesByInvestigation[investigation.id] ?? [],
  evidence: evidence.filter((item) => item.investigationId === investigation.id),
  claims: claims.filter((item) => item.investigationId === investigation.id),
  factualReviews: factualReviews.filter((item) => item.investigationId === investigation.id),
})) satisfies readonly InvestigationDetail[];

const recentActivity = [
  {
    id: "activity-01",
    investigationId: "inv-atlas-meridian",
    occurredAt: "2026-08-31T14:35:00Z",
    summary: "Investigação sintética encaminhada para revisão interna.",
    type: "LIFECYCLE_UPDATED",
  },
  {
    id: "activity-02",
    investigationId: "inv-northstar-components",
    occurredAt: "2026-08-31T11:00:00Z",
    summary: "Claim sintética devolvida para correção.",
    type: "CLAIM_REVIEWED",
  },
  {
    id: "activity-03",
    investigationId: "inv-rheinbruck-machines",
    occurredAt: "2026-08-30T16:30:00Z",
    summary: "Evidence sintética registrada na camada de demonstração.",
    type: "EVIDENCE_RECORDED",
  },
  {
    id: "activity-04",
    investigationId: "inv-solandia-exports",
    occurredAt: "2026-08-30T09:10:00Z",
    summary: "Confirmação humana sintética de entidade registrada.",
    type: "LIFECYCLE_UPDATED",
  },
  {
    id: "activity-05",
    investigationId: "inv-pacifica-renewables",
    occurredAt: "2026-08-29T18:05:00Z",
    summary: "Planejamento sintético da investigação iniciado.",
    type: "LIFECYCLE_UPDATED",
  },
] as const satisfies readonly ActivityItem[];

export const populatedFixtureData: FixtureDataSet = {
  dashboard: {
    asOf: "2026-08-31T15:00:00Z",
    totalInvestigations: investigations.length,
    activeInvestigations: investigations.length,
    investigationsAwaitingReview: 1,
    evidenceItems: evidence.length,
    claims: claims.length,
  },
  investigations,
  investigationDetails,
  evidence,
  claims,
  factualReviews,
  recentActivity,
};

export const emptyFixtureData: FixtureDataSet = {
  dashboard: {
    asOf: "2026-08-31T15:00:00Z",
    totalInvestigations: 0,
    activeInvestigations: 0,
    investigationsAwaitingReview: 0,
    evidenceItems: 0,
    claims: 0,
  },
  investigations: [],
  investigationDetails: [],
  evidence: [],
  claims: [],
  factualReviews: [],
  recentActivity: [],
};
