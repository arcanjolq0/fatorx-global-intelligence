import type {
  ActivityItem,
  AuditEventSummary,
  ClaimReviewSummary,
  ClaimSummary,
  ControlledSourceSummary,
  DashboardSummary,
  EntityCandidate,
  EntitySummary,
  EvidenceSummary,
  InvestigationDetail,
  InvestigationSummary,
  ReportPreviewSummary,
} from "../types";

export interface FixtureDataSet {
  readonly dashboard: DashboardSummary;
  readonly investigations: readonly InvestigationSummary[];
  readonly investigationDetails: readonly InvestigationDetail[];
  readonly evidence: readonly EvidenceSummary[];
  readonly claims: readonly ClaimSummary[];
  readonly factualReviews: readonly ClaimReviewSummary[];
  readonly recentActivity: readonly ActivityItem[];
  readonly controlledSources: readonly ControlledSourceSummary[];
  readonly auditEvents: readonly AuditEventSummary[];
  readonly reportPreviews: readonly ReportPreviewSummary[];
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
    createdAt: "2026-08-28T10:00:00Z",
    friendlyId: "EVD-ATL-002",
    history: [
      {
        occurredAt: "2026-08-28T10:00:00Z",
        summary: "Versão 2 registrada na fixture controlada.",
        type: "RECORDED",
      },
    ],
    id: "ev-atlas-registration",
    investigationId: "inv-atlas-meridian",
    label: "Extrato sintético de registro empresarial",
    kind: "STRUCTURED_DATA",
    locatorSummary: "Registro sintético · seção cadastral",
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture registral controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-atlas-registration",
    version: 2,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "ADMISSIBLE",
    },
  },
  {
    createdAt: "2026-08-28T10:05:00Z",
    friendlyId: "EVD-ATL-003",
    history: [
      {
        occurredAt: "2026-08-28T10:05:00Z",
        summary: "Evidence registrada; decisão efetiva ainda pendente.",
        type: "RECORDED",
      },
    ],
    id: "ev-atlas-address",
    investigationId: "inv-atlas-meridian",
    label: "Referência sintética de endereço operacional",
    kind: "TEXT",
    locatorSummary: "Referência sintética · endereço principal",
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture textual controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-atlas-address",
    version: 1,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "PENDING",
    },
  },
  {
    createdAt: "2026-08-28T10:10:00Z",
    friendlyId: "EVD-ATL-004",
    history: [
      {
        occurredAt: "2026-08-28T10:10:00Z",
        summary: "Evidence registrada com uso efetivo restrito.",
        type: "RECORDED",
      },
    ],
    id: "ev-atlas-filing",
    investigationId: "inv-atlas-meridian",
    label: "Documento societário sintético",
    kind: "TEXT",
    locatorSummary: "Documento sintético · quadro societário",
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture documental controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-atlas-filing",
    version: 1,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "RESTRICTED",
    },
  },
  {
    createdAt: "2026-08-27T09:40:00Z",
    friendlyId: "EVD-ATL-001",
    history: [
      {
        occurredAt: "2026-08-27T09:40:00Z",
        summary: "Versão 1 registrada na fixture controlada.",
        type: "RECORDED",
      },
      {
        occurredAt: "2026-08-28T10:00:00Z",
        summary: "Versão superada pela versão 2 e decisão efetiva revogada.",
        type: "VERSION_SUPERSEDED",
      },
    ],
    id: "ev-atlas-prior-registration",
    investigationId: "inv-atlas-meridian",
    label: "Versão sintética anterior do registro",
    kind: "STRUCTURED_DATA",
    locatorSummary: "Registro sintético · versão histórica",
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture registral controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-atlas-registration",
    version: 1,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "REVOKED",
    },
  },
  {
    createdAt: "2026-08-29T13:30:00Z",
    friendlyId: "EVD-NOR-001",
    history: [
      {
        occurredAt: "2026-08-29T13:30:00Z",
        summary: "Evidence registrada na fixture controlada.",
        type: "RECORDED",
      },
    ],
    id: "ev-northstar-registration",
    investigationId: "inv-northstar-components",
    label: "Extrato sintético de registro empresarial",
    kind: "STRUCTURED_DATA",
    locatorSummary: "Registro sintético · identificação",
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture registral controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-northstar-registration",
    version: 1,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "ADMISSIBLE",
    },
  },
  {
    createdAt: "2026-08-29T13:35:00Z",
    friendlyId: "EVD-NOR-002",
    history: [
      {
        occurredAt: "2026-08-29T13:35:00Z",
        summary: "Referência registrada e decisão efetiva rejeitada.",
        type: "RECORDED",
      },
    ],
    id: "ev-northstar-alias",
    investigationId: "inv-northstar-components",
    label: "Referência sintética de denominação anterior",
    kind: "EXTERNAL_REFERENCE",
    locatorSummary: null,
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture de referência controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-northstar-alias",
    version: 1,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "REJECTED",
    },
  },
  {
    createdAt: "2026-08-29T13:40:00Z",
    friendlyId: "EVD-NOR-003",
    history: [
      {
        occurredAt: "2026-08-29T13:40:00Z",
        summary: "Evidence registrada na fixture controlada.",
        type: "RECORDED",
      },
      {
        occurredAt: "2026-08-31T10:55:00Z",
        summary: "Decisão efetiva passou a Expirada para uso factual interno.",
        type: "EFFECTIVE_STATUS_CHANGED",
      },
    ],
    id: "ev-northstar-status",
    investigationId: "inv-northstar-components",
    label: "Registro sintético de situação cadastral",
    kind: "TEXT",
    locatorSummary: "Registro sintético · situação cadastral",
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture textual controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-northstar-status",
    version: 1,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "EXPIRED",
    },
  },
  {
    createdAt: "2026-08-30T16:30:00Z",
    friendlyId: "EVD-RHE-001",
    history: [
      {
        occurredAt: "2026-08-30T16:30:00Z",
        summary: "Resultado sintético registrado; decisão efetiva pendente.",
        type: "RECORDED",
      },
    ],
    id: "ev-rheinbruck-registration",
    investigationId: "inv-rheinbruck-machines",
    label: "Resultado sintético de coleta controlada",
    kind: "STRUCTURED_DATA",
    locatorSummary: "Coleta simulada · identificação",
    origin: { category: "CONTROLLED_SYNTHETIC_FIXTURE", label: "Fixture de coleta controlada" },
    persistedAdmissibilityStatus: "PENDING",
    seriesId: "evidence-series-rheinbruck-registration",
    version: 1,
    admissibility: {
      purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
      status: "PENDING",
    },
  },
] as const satisfies readonly EvidenceSummary[];

const claims = [
  {
    createdAt: "2026-08-29T14:00:00Z",
    id: "claim-atlas-legal-name",
    investigationId: "inv-atlas-meridian",
    label: "Denominação registrada corresponde a Atlas Meridian Comércio S.A.",
    seriesId: "claim-series-atlas-legal-name",
    version: 1,
    assessment: "SUPPORTED",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-atlas-registration",
        evidenceVersion: 2,
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
    history: [
      {
        occurredAt: "2026-08-29T14:00:00Z",
        summary: "Versão 1 da Claim registrada na fixture.",
        version: 1,
      },
      {
        occurredAt: "2026-08-30T15:00:00Z",
        summary: "Aceita somente para uso factual interno.",
        version: 1,
      },
    ],
  },
  {
    createdAt: "2026-08-29T15:00:00Z",
    id: "claim-atlas-prior-identifier",
    investigationId: "inv-atlas-meridian",
    label: "Identificador anterior permanece aplicável à entidade",
    seriesId: "claim-series-atlas-prior-identifier",
    version: 1,
    assessment: "SUPPORTED",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-atlas-prior-registration",
        evidenceVersion: 1,
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
    history: [
      {
        occurredAt: "2026-08-29T15:00:00Z",
        summary: "Versão 1 da Claim registrada na fixture.",
        version: 1,
      },
      {
        occurredAt: "2026-08-31T09:10:00Z",
        summary: "Aceite invalidado após revogação efetiva da Evidence vinculada.",
        version: 1,
      },
    ],
  },
  {
    createdAt: "2026-08-30T09:30:00Z",
    id: "claim-northstar-registration",
    investigationId: "inv-northstar-components",
    label: "Identificador sintético corresponde ao registro apresentado",
    seriesId: "claim-series-northstar-registration",
    version: 1,
    assessment: "SUPPORTED",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-northstar-registration",
        evidenceVersion: 1,
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
    history: [
      {
        occurredAt: "2026-08-30T09:30:00Z",
        summary: "Versão 1 da Claim registrada; revisão factual pendente.",
        version: 1,
      },
    ],
  },
  {
    createdAt: "2026-08-30T09:40:00Z",
    id: "claim-northstar-alias",
    investigationId: "inv-northstar-components",
    label: "Denominação anterior pode ser usada como nome vigente",
    seriesId: "claim-series-northstar-alias",
    version: 1,
    assessment: "INSUFFICIENT",
    criticality: "STANDARD",
    evidenceUses: [
      {
        evidenceId: "ev-northstar-alias",
        evidenceVersion: 1,
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
    history: [
      {
        occurredAt: "2026-08-30T09:40:00Z",
        summary: "Versão 1 da Claim registrada na fixture.",
        version: 1,
      },
      {
        occurredAt: "2026-08-31T10:45:00Z",
        summary: "Rejeitada para uso factual interno.",
        version: 1,
      },
    ],
  },
  {
    createdAt: "2026-08-30T10:00:00Z",
    id: "claim-northstar-registration-status",
    investigationId: "inv-northstar-components",
    label: "Situação cadastral permanece ativa no período observado",
    seriesId: "claim-series-northstar-registration-status",
    version: 2,
    assessment: "CONFLICTED",
    criticality: "CRITICAL",
    evidenceUses: [
      {
        evidenceId: "ev-northstar-registration",
        evidenceVersion: 1,
        role: "SUPPORTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "ELIGIBLE" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "ADMISSIBLE",
        },
      },
      {
        evidenceId: "ev-northstar-status",
        evidenceVersion: 1,
        role: "CONTRADICTS",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "ELIGIBLE" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "EXPIRED",
        },
      },
      {
        evidenceId: "ev-northstar-alias",
        evidenceVersion: 1,
        role: "QUALIFIES",
        eligibility: { purpose: "INTERNAL_CLAIM_VERIFICATION", status: "RESTRICTED" },
        admissibility: {
          purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
          status: "REJECTED",
        },
      },
    ],
    factualReview: {
      purpose: "INTERNAL_FACTUAL_CLAIM_USE",
      decisionOutcome: "NEEDS_CORRECTION",
      effectiveStatus: "NEEDS_CORRECTION",
      reviewedAt: "2026-08-31T11:00:00Z",
    },
    history: [
      {
        occurredAt: "2026-08-30T10:00:00Z",
        summary: "Versão 1 registrada com base inicial.",
        version: 1,
      },
      {
        occurredAt: "2026-08-31T10:50:00Z",
        summary: "Versão 2 adicionou vínculo contraditório e qualificador explícitos.",
        version: 2,
      },
      {
        occurredAt: "2026-08-31T11:00:00Z",
        summary: "Versão 2 devolvida para correção factual.",
        version: 2,
      },
    ],
  },
] as const satisfies readonly ClaimSummary[];

const reviewMetadata = [
  {
    claimId: "claim-atlas-legal-name",
    decisionNote: "Base sintética considerada suficiente somente para uso factual interno.",
    invalidationReason: null,
    reviewer: { displayName: "Marina Costa", id: "reviewer-01" },
  },
  {
    claimId: "claim-atlas-prior-identifier",
    decisionNote: "Decisão histórica preservada para rastreabilidade.",
    invalidationReason: "A Evidence exata vinculada recebeu estado efetivo Revogado.",
    reviewer: { displayName: "Rafael Nunes", id: "reviewer-02" },
  },
  {
    claimId: "claim-northstar-registration",
    decisionNote: null,
    invalidationReason: null,
    reviewer: null,
  },
  {
    claimId: "claim-northstar-alias",
    decisionNote: "A base não sustenta uso da denominação como nome vigente.",
    invalidationReason: null,
    reviewer: { displayName: "Marina Costa", id: "reviewer-01" },
  },
  {
    claimId: "claim-northstar-registration-status",
    decisionNote: "Contradição explícita exige correção da Claim antes de nova revisão.",
    invalidationReason: null,
    reviewer: { displayName: "Rafael Nunes", id: "reviewer-02" },
  },
] as const;

const factualReviews = claims.map((claim, index) => {
  const metadata = reviewMetadata[index];
  if (metadata?.claimId !== claim.id) {
    throw new Error("Fixture de revisão factual desalinhada com a Claim.");
  }
  return {
    id: `review-${String(index + 1).padStart(2, "0")}`,
    claimId: claim.id,
    claimVersion: claim.version,
    investigationId: claim.investigationId,
    decisionNote: metadata.decisionNote,
    invalidationReason: metadata.invalidationReason,
    reviewer: metadata.reviewer,
    ...claim.factualReview,
  };
}) satisfies readonly ClaimReviewSummary[];

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

const controlledSources = [
  {
    coverage: [
      entities.atlasMeridian.jurisdiction,
      entities.northstar.jurisdiction,
      entities.rheinbruck.jurisdiction,
    ],
    id: "fixture.controlled.registry",
    kind: "SYNTHETIC_REGISTRY",
    label: "Canal registral sintético",
    limitations: [
      "Dados inteiramente fictícios e mantidos no repositório.",
      "Sem acesso de rede, licença de provedor ou cobertura produtiva.",
    ],
    status: "CONTROLLED_TEST_FIXTURE",
    validatedAt: "2026-08-31T12:00:00Z",
  },
  {
    coverage: [entities.atlasMeridian.jurisdiction, entities.northstar.jurisdiction],
    id: "fixture.controlled.text",
    kind: "CONTROLLED_TEXT_CORPUS",
    label: "Corpus textual controlado",
    limitations: [
      "Textos sintéticos para exercitar proveniência e revisão.",
      "Não representa publicação, órgão ou fonte externa real.",
    ],
    status: "CONTROLLED_TEST_FIXTURE",
    validatedAt: "2026-08-31T12:05:00Z",
  },
  {
    coverage: [entities.atlasMeridian.jurisdiction],
    id: "fixture.controlled.documents",
    kind: "CONTROLLED_DOCUMENT_CORPUS",
    label: "Corpus documental controlado",
    limitations: [
      "Documentos de demonstração sem valor oficial.",
      "Sem ingestão, atualização ou retenção de documentos reais.",
    ],
    status: "CONTROLLED_TEST_FIXTURE",
    validatedAt: "2026-08-31T12:10:00Z",
  },
  {
    coverage: [entities.northstar.jurisdiction],
    id: "fixture.controlled.references",
    kind: "CONTROLLED_REFERENCE_CORPUS",
    label: "Referências externas simuladas",
    limitations: [
      "Referências não resolvem para URLs externas.",
      "Canal suspenso no cenário de teste para demonstrar indisponibilidade.",
    ],
    status: "TEST_SUSPENDED",
    validatedAt: "2026-08-31T12:15:00Z",
  },
] as const satisfies readonly ControlledSourceSummary[];

const auditEvents = [
  {
    action: "Encaminhamento para revisão interna",
    actor: null,
    category: "INVESTIGATION",
    id: "audit-01",
    investigationId: "inv-atlas-meridian",
    objectReference: "inv-atlas-meridian",
    occurredAt: "2026-08-31T14:35:00Z",
    result: "PENDING",
  },
  {
    action: "Revisão factual devolvida para correção",
    actor: { displayName: "Rafael Nunes", id: "reviewer-02" },
    category: "FACTUAL_REVIEW",
    id: "audit-02",
    investigationId: "inv-northstar-components",
    objectReference: "claim-northstar-registration-status · v2",
    occurredAt: "2026-08-31T11:00:00Z",
    result: "NEEDS_ATTENTION",
  },
  {
    action: "Decisão factual invalidada",
    actor: { displayName: "Rafael Nunes", id: "reviewer-02" },
    category: "FACTUAL_REVIEW",
    id: "audit-03",
    investigationId: "inv-atlas-meridian",
    objectReference: "claim-atlas-prior-identifier · v1",
    occurredAt: "2026-08-31T09:10:00Z",
    result: "INVALIDATED",
  },
  {
    action: "Evidence registrada na camada de demonstração",
    actor: null,
    category: "EVIDENCE",
    id: "audit-04",
    investigationId: "inv-rheinbruck-machines",
    objectReference: "EVD-RHE-001 · v1",
    occurredAt: "2026-08-30T16:30:00Z",
    result: "RECORDED",
  },
  {
    action: "Confirmação humana de entidade registrada",
    actor: null,
    category: "ENTITY",
    id: "audit-05",
    investigationId: "inv-solandia-exports",
    objectReference: "entity-solandia-exports",
    occurredAt: "2026-08-30T09:10:00Z",
    result: "RECORDED",
  },
  {
    action: "Claim registrada para revisão factual",
    actor: null,
    category: "CLAIM",
    id: "audit-06",
    investigationId: "inv-northstar-components",
    objectReference: "claim-northstar-registration · v1",
    occurredAt: "2026-08-30T09:30:00Z",
    result: "PENDING",
  },
] as const satisfies readonly AuditEventSummary[];

const reportPreviews = investigations.map((investigation) => {
  if (investigation.id === "inv-atlas-meridian") {
    return {
      asOf: "2026-08-31T15:00:00Z",
      availability: "PREVIEW_AVAILABLE",
      id: "report-preview-atlas",
      investigationId: investigation.id,
      limitations: [
        "Prévia visual local; não é relatório produtivo nem documento aprovado.",
        "Contém somente Claims aceitas para uso factual interno e sua Evidence exata.",
        "Não contém risk score, decisão de crédito, assinatura ou garantia de verdade externa.",
      ],
      traceability: [
        {
          claimId: "claim-atlas-legal-name",
          claimVersion: 1,
          evidence: [{ evidenceId: "ev-atlas-registration", evidenceVersion: 2 }],
          factualReviewId: "review-01",
        },
      ],
    } as const;
  }

  return {
    asOf: "2026-08-31T15:00:00Z",
    availability: "NOT_AVAILABLE",
    id: `report-preview-${investigation.id}`,
    investigationId: investigation.id,
    limitations: [
      "Nenhuma Claim aceita para uso factual interno está disponível nesta fixture.",
      "A indisponibilidade não constitui conclusão sobre a entidade investigada.",
    ],
    traceability: [],
  } as const;
}) satisfies readonly ReportPreviewSummary[];

export const populatedFixtureData: FixtureDataSet = {
  dashboard: {
    asOf: "2026-08-31T15:00:00Z",
    totalInvestigations: investigations.length,
    activeInvestigations: investigations.length,
    investigationsAwaitingReview: 1,
    evidenceItems: evidence.length,
    claims: claims.length,
    pendingReviews: factualReviews.filter((review) => review.effectiveStatus === "PENDING").length,
  },
  investigations,
  investigationDetails,
  evidence,
  claims,
  factualReviews,
  recentActivity,
  controlledSources,
  auditEvents,
  reportPreviews,
};

export const emptyFixtureData: FixtureDataSet = {
  dashboard: {
    asOf: "2026-08-31T15:00:00Z",
    totalInvestigations: 0,
    activeInvestigations: 0,
    investigationsAwaitingReview: 0,
    evidenceItems: 0,
    claims: 0,
    pendingReviews: 0,
  },
  investigations: [],
  investigationDetails: [],
  evidence: [],
  claims: [],
  factualReviews: [],
  recentActivity: [],
  controlledSources: [],
  auditEvents: [],
  reportPreviews: [],
};
