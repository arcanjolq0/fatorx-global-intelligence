import type { BadgeTone } from "../components/ui/Badge";
import type {
  AuditEventCategory,
  AuditEventResult,
  ControlledSourceKind,
  ControlledSourceSummary,
  ReportPreviewSummary,
} from "../data/types";

export const controlledSourceKindLabels: Readonly<Record<ControlledSourceKind, string>> = {
  SYNTHETIC_REGISTRY: "Registro sintético",
  CONTROLLED_TEXT_CORPUS: "Corpus textual controlado",
  CONTROLLED_DOCUMENT_CORPUS: "Corpus documental controlado",
  CONTROLLED_REFERENCE_CORPUS: "Referências simuladas",
};

export const controlledSourceStatusLabels: Readonly<
  Record<ControlledSourceSummary["status"], string>
> = {
  CONTROLLED_TEST_FIXTURE: "TEST · fixture controlada",
  TEST_SUSPENDED: "TEST · suspensa",
};

export const auditCategoryLabels: Readonly<Record<AuditEventCategory, string>> = {
  INVESTIGATION: "Investigação",
  ENTITY: "Entidade",
  EVIDENCE: "Evidence",
  CLAIM: "Claim",
  FACTUAL_REVIEW: "Revisão factual",
};

export const auditResultLabels: Readonly<Record<AuditEventResult, string>> = {
  RECORDED: "Registrado",
  PENDING: "Pendente",
  NEEDS_ATTENTION: "Requer atenção",
  INVALIDATED: "Invalidado",
};

export const reportAvailabilityLabels: Readonly<
  Record<ReportPreviewSummary["availability"], string>
> = {
  PREVIEW_AVAILABLE: "Prévia disponível",
  NOT_AVAILABLE: "Prévia indisponível",
};

export function getAuditResultTone(result: AuditEventResult): BadgeTone {
  if (result === "RECORDED") return "success";
  if (result === "PENDING" || result === "NEEDS_ATTENTION") return "warning";
  return "danger";
}
