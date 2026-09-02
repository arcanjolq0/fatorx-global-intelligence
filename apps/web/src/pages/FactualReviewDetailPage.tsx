import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { ClaimEvidenceList } from "../components/intelligence/ClaimEvidenceList";
import { CollectionLoading } from "../components/intelligence/CollectionPageState";
import {
  ReviewStatusBadge,
  SemanticStatusGroup,
} from "../components/intelligence/StatusComponents";
import { Card, StatePanel } from "../components/ui";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type {
  ClaimReviewSummary,
  ClaimSummary,
  EvidenceSummary,
  InvestigationSummary,
} from "../data/types";

type ReviewDetailState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "not-found" }
  | {
      readonly status: "ready";
      readonly review: ClaimReviewSummary;
      readonly claims: readonly ClaimSummary[];
      readonly evidence: readonly EvidenceSummary[];
      readonly investigations: readonly InvestigationSummary[];
    };

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function FactualReviewDetailPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const { reviewId = "" } = useParams<{ reviewId: string }>();
  const [state, setState] = useState<ReviewDetailState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([
      dataSource.getFactualReviewDetail(reviewId),
      dataSource.listClaims(),
      dataSource.listEvidence(),
      dataSource.listInvestigations(),
    ]).then(
      ([review, claims, evidence, investigations]) => {
        if (!isCurrent) return;
        setState(
          review === null
            ? { status: "not-found" }
            : { status: "ready", review, claims, evidence, investigations },
        );
      },
      () => {
        if (isCurrent) setState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [dataSource, retryVersion, reviewId]);

  if (state.status === "loading")
    return <CollectionLoading label="Carregando detalhe da revisão" />;
  if (state.status === "error")
    return (
      <StatePanel
        actionLabel="Tentar novamente"
        kind="error"
        onAction={() => {
          setState({ status: "loading" });
          setRetryVersion((current) => current + 1);
        }}
        title="Não foi possível carregar a revisão"
      >
        Os dados sintéticos locais não foram carregados; nenhum backend foi consultado.
      </StatePanel>
    );
  if (state.status === "not-found")
    return (
      <StatePanel kind="empty" title="Revisão não encontrada">
        O identificador não corresponde ao modelo de leitura sintético.
        <div className="state-panel__inline-action">
          <Link className="button button--secondary" to="/revisoes">
            Ver revisões
          </Link>
        </div>
      </StatePanel>
    );

  const claim = new Map(state.claims.map((item) => [item.id, item])).get(state.review.claimId);
  if (claim?.version !== state.review.claimVersion)
    return (
      <StatePanel kind="error" title="Base factual incoerente">
        A versão exata da Claim não está disponível no modelo de leitura. A revisão não pode ser
        apresentada como válida.
      </StatePanel>
    );
  const investigation = new Map(state.investigations.map((item) => [item.id, item])).get(
    state.review.investigationId,
  );
  const evidenceById = new Map(state.evidence.map((item) => [item.id, item]));
  const supports = claim.evidenceUses.filter((item) => item.role === "SUPPORTS").length;
  const contradicts = claim.evidenceUses.filter((item) => item.role === "CONTRADICTS").length;
  const qualifies = claim.evidenceUses.filter((item) => item.role === "QUALIFIES").length;

  return (
    <div className="page-stack detail-record-page">
      <section aria-labelledby="review-detail-title" className="detail-hero">
        <div>
          <p className="eyebrow">
            {state.review.id} · Claim v{state.review.claimVersion}
          </p>
          <h2 id="review-detail-title">{claim.label}</h2>
          <p>{investigation?.entity.legalName ?? state.review.investigationId}</p>
        </div>
        <div className="detail-hero__status">
          <ReviewStatusBadge status={state.review.effectiveStatus} />
          <span>Somente leitura</span>
        </div>
      </section>
      <p className="semantic-boundary-banner">
        <strong>Decisão F5.4 limitada:</strong> aceita ou rejeita uma versão exata somente para uso
        factual interno; não declara verdade, reportabilidade ou risco.
      </p>
      <section className="detail-columns">
        <Card title="Decisão e responsável">
          <dl className="stacked-definition-list review-definition-list">
            <div>
              <dt>Revisor</dt>
              <dd>{state.review.reviewer?.displayName ?? "Não atribuído"}</dd>
            </div>
            <div>
              <dt>Decidida em</dt>
              <dd>
                {state.review.reviewedAt === null
                  ? "Pendente"
                  : dateFormatter.format(new Date(state.review.reviewedAt))}
              </dd>
            </div>
            <div>
              <dt>Justificativa resumida</dt>
              <dd>{state.review.decisionNote ?? "Sem decisão registrada."}</dd>
            </div>
            {state.review.invalidationReason === null ? null : (
              <div>
                <dt>Motivo da invalidação</dt>
                <dd>{state.review.invalidationReason}</dd>
              </div>
            )}
          </dl>
        </Card>
        <Card title="Resumo da base factual">
          <dl className="basis-counts">
            <div>
              <dt>Sustenta</dt>
              <dd>{supports}</dd>
            </div>
            <div>
              <dt>Contradiz</dt>
              <dd>{contradicts}</dd>
            </div>
            <div>
              <dt>Qualifica</dt>
              <dd>{qualifies}</dd>
            </div>
          </dl>
          <p className="card__summary">Contagens rastreáveis; não são score ou cálculo de risco.</p>
        </Card>
      </section>
      <Card title="F5.2 · F5.3 · F5.4">
        <SemanticStatusGroup
          evidenceUses={claim.evidenceUses}
          reviewStatus={state.review.effectiveStatus}
        />
      </Card>
      <Card title="Evidence considerada na versão">
        <ClaimEvidenceList evidenceById={evidenceById} evidenceUses={claim.evidenceUses} />
      </Card>
      <Link className="text-link" to="/revisoes">
        Voltar para revisões
      </Link>
    </div>
  );
}
