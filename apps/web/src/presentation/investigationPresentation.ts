import type {
  ClaimSummary,
  ContextualEligibilityStatus,
  EffectiveEvidenceAdmissibilityStatus,
  EffectiveFactualReviewStatus,
  EvidenceKind,
  EvidenceRole,
  InvestigationLifecycleStatus,
} from "../data/types";
import type { BadgeTone } from "../components/ui/Badge";

export const investigationStatusLabels: Readonly<Record<InvestigationLifecycleStatus, string>> = {
  CREATED: "Criada",
  IDENTIFYING: "Identificando",
  WAITING_FOR_ENTITY_CONFIRMATION: "Aguardando entidade",
  PLANNING: "Planejamento",
  COLLECTING: "Coleta",
  NORMALIZING: "Normalização",
  VERIFYING: "Verificação",
  ANALYZING: "Análise",
  WAITING_FOR_REVIEW: "Aguardando revisão",
  COMPLETED: "Concluída",
  PARTIALLY_COMPLETED: "Parcialmente concluída",
  FAILED: "Falhou",
  CANCELLED: "Cancelada",
};

export const evidenceStatusLabels: Readonly<Record<EffectiveEvidenceAdmissibilityStatus, string>> =
  {
    PENDING: "Pendente",
    ADMISSIBLE: "Admissível para uso factual interno",
    RESTRICTED: "Restrita",
    EXPIRED: "Expirada",
    REVOKED: "Revogada",
    REJECTED: "Rejeitada",
  };

export const factualReviewStatusLabels: Readonly<Record<EffectiveFactualReviewStatus, string>> = {
  PENDING: "Revisão pendente",
  ACCEPTED: "Aceita para uso factual interno",
  REJECTED: "Rejeitada para uso factual interno",
  NEEDS_CORRECTION: "Requer correção",
  INVALIDATED: "Decisão invalidada",
};

export const eligibilityStatusLabels: Readonly<Record<ContextualEligibilityStatus, string>> = {
  ELIGIBLE: "Elegível no contexto",
  RESTRICTED: "Elegibilidade restrita",
  REJECTED: "Não elegível",
};

export const evidenceKindLabels: Readonly<Record<EvidenceKind, string>> = {
  TEXT: "Texto",
  STRUCTURED_DATA: "Dados estruturados",
  IMAGE: "Imagem",
  EXTERNAL_REFERENCE: "Referência externa",
};

export const evidenceRoleLabels: Readonly<Record<EvidenceRole, string>> = {
  SUPPORTS: "Sustenta",
  CONTRADICTS: "Contradiz",
  QUALIFIES: "Qualifica",
};

export const claimAssessmentLabels: Readonly<Record<ClaimSummary["assessment"], string>> = {
  INSUFFICIENT: "Base insuficiente",
  SUPPORTED: "Com suporte",
  CONFLICTED: "Com contradição",
};

export function getEligibilityStatusTone(status: ContextualEligibilityStatus): BadgeTone {
  if (status === "ELIGIBLE") return "success";
  if (status === "RESTRICTED") return "warning";
  return "danger";
}

export function getEvidenceRoleTone(role: EvidenceRole): BadgeTone {
  if (role === "SUPPORTS") return "success";
  if (role === "CONTRADICTS") return "danger";
  return "info";
}

export function getInvestigationStatusTone(status: InvestigationLifecycleStatus): BadgeTone {
  if (status === "COMPLETED") return "success";
  if (status === "FAILED" || status === "CANCELLED") return "danger";
  if (status === "WAITING_FOR_ENTITY_CONFIRMATION" || status === "WAITING_FOR_REVIEW") {
    return "warning";
  }
  if (status === "CREATED") return "neutral";
  return "info";
}

export function getEvidenceStatusTone(status: EffectiveEvidenceAdmissibilityStatus): BadgeTone {
  if (status === "ADMISSIBLE") return "success";
  if (status === "PENDING" || status === "RESTRICTED") return "warning";
  if (status === "REJECTED" || status === "REVOKED") return "danger";
  return "neutral";
}

export function getReviewStatusTone(status: EffectiveFactualReviewStatus): BadgeTone {
  if (status === "ACCEPTED") return "success";
  if (status === "PENDING" || status === "NEEDS_CORRECTION") return "warning";
  return "danger";
}
