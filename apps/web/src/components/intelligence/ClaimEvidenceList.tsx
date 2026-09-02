import type { EvidenceSummary, EvidenceUsePresentation } from "../../data/types";
import {
  EvidenceRoleBadge,
  EvidenceStatusBadge,
  ContextualEligibilityBadge,
} from "./StatusComponents";

export function ClaimEvidenceList({
  evidenceById,
  evidenceUses,
}: {
  readonly evidenceById: ReadonlyMap<string, EvidenceSummary>;
  readonly evidenceUses: readonly EvidenceUsePresentation[];
}) {
  if (evidenceUses.length === 0) {
    return <p className="empty-inline">Nenhum vínculo de Evidence registrado para esta versão.</p>;
  }

  return (
    <ul className="claim-evidence-list">
      {evidenceUses.map((evidenceUse) => {
        const evidence = evidenceById.get(evidenceUse.evidenceId);
        return (
          <li key={`${evidenceUse.evidenceId}-${evidenceUse.role}`}>
            <div className="claim-evidence-list__heading">
              <span>
                <strong>{evidence?.friendlyId ?? evidenceUse.evidenceId}</strong>
                <small>Evidence v{evidenceUse.evidenceVersion}</small>
              </span>
              <EvidenceRoleBadge role={evidenceUse.role} />
            </div>
            <p>{evidence?.label ?? "Evidence não disponível no modelo de leitura sintético."}</p>
            <div className="claim-evidence-list__semantics">
              <span>
                <small>F5.2 · vínculo</small>
                <ContextualEligibilityBadge status={evidenceUse.eligibility.status} />
              </span>
              <span>
                <small>F5.3 · Evidence</small>
                <EvidenceStatusBadge status={evidenceUse.admissibility.status} />
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
