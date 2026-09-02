import { useEffect, useState } from "react";

import { ClaimEvidenceList } from "../components/intelligence/ClaimEvidenceList";
import { ClaimStatusStack, ReviewStatusBadge } from "../components/intelligence/StatusComponents";
import { CollectionError, CollectionLoading } from "../components/intelligence/CollectionPageState";
import { Badge, Card, Select, StatePanel } from "../components/ui";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type {
  ClaimReviewSummary,
  ClaimSummary,
  EvidenceSummary,
  InvestigationSummary,
  ReportPreviewSummary,
} from "../data/types";
import { reportAvailabilityLabels } from "../presentation/governancePresentation";

type ReportsState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | {
      readonly status: "ready";
      readonly claims: readonly ClaimSummary[];
      readonly evidence: readonly EvidenceSummary[];
      readonly investigations: readonly InvestigationSummary[];
      readonly reports: readonly ReportPreviewSummary[];
      readonly reviews: readonly ClaimReviewSummary[];
    };

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function ReportsPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const [state, setState] = useState<ReportsState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);
  const [selectedInvestigationId, setSelectedInvestigationId] = useState("");

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([
      dataSource.listReportPreviews(),
      dataSource.listInvestigations(),
      dataSource.listClaims(),
      dataSource.listFactualReviews(),
      dataSource.listEvidence(),
    ]).then(
      ([reports, investigations, claims, reviews, evidence]) => {
        if (isCurrent)
          setState({ status: "ready", reports, investigations, claims, reviews, evidence });
      },
      () => {
        if (isCurrent) setState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [dataSource, retryVersion]);

  if (state.status === "loading")
    return <CollectionLoading label="Carregando previews de relatório" />;
  if (state.status === "error") {
    return (
      <CollectionError
        onRetry={() => {
          setState({ status: "loading" });
          setRetryVersion((current) => current + 1);
        }}
      />
    );
  }

  const firstReport = state.reports[0];
  if (firstReport === undefined || state.investigations.length === 0) {
    return (
      <StatePanel kind="empty" title="Nenhum preview de relatório disponível">
        A fixture selecionada não contém investigações. Nenhum relatório foi gerado ou solicitado.
      </StatePanel>
    );
  }

  const selectedReport =
    state.reports.find((report) => report.investigationId === selectedInvestigationId) ??
    firstReport;
  const selectedInvestigation = state.investigations.find(
    (investigation) => investigation.id === selectedReport.investigationId,
  );
  const claimById = new Map(state.claims.map((claim) => [claim.id, claim]));
  const reviewById = new Map(state.reviews.map((review) => [review.id, review]));
  const evidenceById = new Map(state.evidence.map((evidence) => [evidence.id, evidence]));

  return (
    <div className="page-stack governance-page reports-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">Representação não produtiva</p>
          <h2>Preview rastreável de relatório</h2>
          <p>
            Visualização local para validar hierarquia e linhagem, sem gerar, exportar, aprovar ou
            assinar documentos.
          </p>
        </div>
        <Badge tone="warning">Preview / mock</Badge>
      </section>
      <p className="semantic-boundary-banner semantic-boundary-banner--strong">
        <strong>Este preview não é um relatório produtivo.</strong>
        Não há PDF, exportação, assinatura, aprovação, risk score ou decisão de crédito. Aceite F5.4
        significa somente uso factual interno da versão exata da Claim.
      </p>

      <Card className="report-selector">
        <Select
          aria-label="Investigação do preview"
          helperText="A seleção é local e não dispara geração nem consulta de backend."
          label="Investigação do preview"
          onChange={(event) => {
            setSelectedInvestigationId(event.currentTarget.value);
          }}
          options={state.investigations.map((investigation) => ({
            label: investigation.entity.legalName,
            value: investigation.id,
          }))}
          value={selectedReport.investigationId}
        />
      </Card>

      <Card className="report-preview-shell">
        <header className="report-preview-heading">
          <div>
            <p className="card__eyebrow">{selectedReport.id}</p>
            <h3>{selectedInvestigation?.entity.legalName ?? selectedReport.investigationId}</h3>
            <p>
              Posição sintética em{" "}
              <time dateTime={selectedReport.asOf}>
                {dateFormatter.format(new Date(selectedReport.asOf))}
              </time>
            </p>
          </div>
          <Badge tone={selectedReport.availability === "PREVIEW_AVAILABLE" ? "success" : "neutral"}>
            {reportAvailabilityLabels[selectedReport.availability]}
          </Badge>
        </header>

        {selectedReport.availability === "NOT_AVAILABLE" ? (
          <StatePanel kind="unavailable" title="Sem base factual aceita para o preview">
            A ausência de Claims aceitas para uso factual interno impede esta representação. Isso
            não é uma conclusão sobre a entidade.
          </StatePanel>
        ) : (
          <section aria-labelledby="traceability-title" className="report-traceability">
            <div className="report-section-heading">
              <div>
                <p className="card__eyebrow">Linhagem factual</p>
                <h4 id="traceability-title">Relatório → Claim → revisão factual → Evidence</h4>
              </div>
              <span>{selectedReport.traceability.length} Claim(s) aceita(s)</span>
            </div>
            {selectedReport.traceability.map((entry) => {
              const claim = claimById.get(entry.claimId);
              const review = reviewById.get(entry.factualReviewId);
              if (claim === undefined || review === undefined) return null;
              const evidenceUses = claim.evidenceUses.filter((use) =>
                entry.evidence.some(
                  (reference) =>
                    reference.evidenceId === use.evidenceId &&
                    reference.evidenceVersion === use.evidenceVersion,
                ),
              );
              return (
                <article
                  className="traceability-chain"
                  key={`${entry.claimId}-${String(entry.claimVersion)}`}
                >
                  <div className="traceability-node traceability-node--claim">
                    <p className="card__eyebrow">Claim exata · v{entry.claimVersion}</p>
                    <h5>{claim.label}</h5>
                    <ClaimStatusStack
                      evidenceUses={evidenceUses}
                      reviewStatus={review.effectiveStatus}
                    />
                  </div>
                  <div className="traceability-node">
                    <p className="card__eyebrow">Revisão factual · {review.id}</p>
                    <ReviewStatusBadge status={review.effectiveStatus} />
                    <p>{review.decisionNote ?? "Sem nota de decisão na fixture."}</p>
                    <small>Revisor: {review.reviewer?.displayName ?? "Não atribuído"}</small>
                  </div>
                  <div className="traceability-node">
                    <p className="card__eyebrow">Evidence exata e papéis</p>
                    <ClaimEvidenceList evidenceById={evidenceById} evidenceUses={evidenceUses} />
                  </div>
                </article>
              );
            })}
          </section>
        )}

        <section aria-labelledby="report-limitations-title" className="report-limitations">
          <h4 id="report-limitations-title">Limitações explícitas</h4>
          <ul>
            {selectedReport.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </section>
      </Card>
    </div>
  );
}
