import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { Badge, Card, Skeleton, StatePanel } from "../components/ui";
import { EvidenceCollection } from "../components/intelligence/EvidenceCollection";
import { ClaimsCollection } from "../components/intelligence/ClaimsCollection";
import { ReviewsCollection } from "../components/intelligence/ReviewsCollection";
import { Timeline } from "../components/intelligence/Timeline";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type { ActivityItem, ClaimSummary, InvestigationDetail } from "../data/types";
import {
  evidenceStatusLabels,
  factualReviewStatusLabels,
  getEvidenceStatusTone,
  getInvestigationStatusTone,
  getReviewStatusTone,
  investigationStatusLabels,
} from "../presentation/investigationPresentation";

interface InvestigationDetailPageProps {
  readonly dataSource?: IntelligenceDataSource;
}

type DetailLoadState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "not-found" }
  | {
      readonly status: "ready";
      readonly detail: InvestigationDetail;
      readonly activity: readonly ActivityItem[];
    };

const tabs = [
  { id: "overview", label: "Visão geral" },
  { id: "entity", label: "Entidade" },
  { id: "evidence", label: "Evidências" },
  { id: "claims", label: "Claims" },
  { id: "reviews", label: "Revisões" },
  { id: "history", label: "Histórico" },
] as const;
type DetailTabId = (typeof tabs)[number]["id"];
const validTabIds = new Set<DetailTabId>(tabs.map((tab) => tab.id));

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

function formatDate(value: string): string {
  return dateFormatter.format(new Date(value));
}

function isAttentionClaim(claim: ClaimSummary): boolean {
  return claim.assessment === "CONFLICTED" || claim.factualReview.effectiveStatus !== "ACCEPTED";
}

function DetailLoading() {
  return (
    <div
      aria-busy="true"
      aria-label="Carregando detalhe da investigação"
      className="detail-loading"
      role="status"
    >
      <Skeleton height="7rem" />
      <div className="summary-grid">
        <Skeleton height="7rem" />
        <Skeleton height="7rem" />
        <Skeleton height="7rem" />
      </div>
      <Skeleton height="16rem" />
    </div>
  );
}

function InvestigationOverview({
  activity,
  detail,
}: {
  readonly activity: readonly ActivityItem[];
  readonly detail: InvestigationDetail;
}) {
  const attentionClaims = detail.claims.filter(isAttentionClaim);
  const contradictions = detail.claims.filter((claim) => claim.assessment === "CONFLICTED");
  return (
    <div className="detail-tab-stack">
      <section aria-label="Resumo da investigação" className="summary-grid">
        <Card>
          <p className="card__eyebrow">Evidências</p>
          <strong className="summary-value">
            {detail.evidence.length.toLocaleString("pt-BR")}
          </strong>
          <p className="card__summary">Itens sintéticos vinculados</p>
        </Card>
        <Card>
          <p className="card__eyebrow">Claims</p>
          <strong className="summary-value">{detail.claims.length.toLocaleString("pt-BR")}</strong>
          <p className="card__summary">Afirmações estruturadas na fixture</p>
        </Card>
        <Card>
          <p className="card__eyebrow">Revisões pendentes</p>
          <strong className="summary-value">
            {detail.pendingReviewCount.toLocaleString("pt-BR")}
          </strong>
          <p className="card__summary">Sem inferência de risco ou score</p>
        </Card>
      </section>

      <section className="detail-columns">
        <Card title="Estado atual">
          <div className="current-state">
            <Badge tone={getInvestigationStatusTone(detail.lifecycleStatus)}>
              {investigationStatusLabels[detail.lifecycleStatus]}
            </Badge>
            <p>
              Este estado vem do read model sintético e não representa execução de connector, fonte
              real ou transição no backend.
            </p>
          </div>
        </Card>
        <Card title="Atividade recente">
          <Timeline
            entries={activity.slice(0, 4).map((item) => ({
              id: item.id,
              occurredAt: item.occurredAt,
              title: item.summary,
            }))}
          />
        </Card>
      </section>

      <section className="detail-columns">
        <Card title="Evidências em destaque">
          {detail.evidence.length === 0 ? (
            <p className="empty-inline">Nenhuma Evidence sintética vinculada.</p>
          ) : (
            <ul className="data-list">
              {detail.evidence.slice(0, 3).map((evidence) => (
                <li key={evidence.id}>
                  <span>
                    <strong>{evidence.label}</strong>
                    <small>{evidence.kind.replaceAll("_", " ")}</small>
                  </span>
                  <Badge tone={getEvidenceStatusTone(evidence.admissibility.status)}>
                    {evidenceStatusLabels[evidence.admissibility.status]}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Claims que exigem atenção">
          {attentionClaims.length === 0 ? (
            <p className="empty-inline">Nenhuma Claim sintética exige atenção.</p>
          ) : (
            <ul className="data-list">
              {attentionClaims.slice(0, 3).map((claim) => (
                <li key={claim.id}>
                  <span>
                    <strong>{claim.label}</strong>
                    <small>
                      {claim.assessment === "CONFLICTED"
                        ? "Assessment conflitado"
                        : "Revisão interna"}
                    </small>
                  </span>
                  <Badge tone={getReviewStatusTone(claim.factualReview.effectiveStatus)}>
                    {factualReviewStatusLabels[claim.factualReview.effectiveStatus]}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <Card title="Contradições relevantes">
        {contradictions.length === 0 ? (
          <p className="empty-inline">Nenhuma contradição explícita na fixture atual.</p>
        ) : (
          <ul className="contradiction-list">
            {contradictions.map((claim) => (
              <li key={claim.id}>
                <strong>{claim.label}</strong>
                <span>
                  {claim.evidenceUses.filter((use) => use.role === "CONTRADICTS").length} vínculo(s)
                  contraditório(s) explícito(s). Isso não torna a Claim falsa.
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function InvestigationEntity({ detail }: { readonly detail: InvestigationDetail }) {
  const isConfirmed = detail.entity.confirmation.status === "CONFIRMED";
  return (
    <div className="detail-tab-stack">
      <Card className="entity-record-card">
        <div className="entity-record-heading">
          <div>
            <p className="card__eyebrow">Registro de identidade</p>
            <h3>{detail.entity.legalName}</h3>
          </div>
          <Badge tone={isConfirmed ? "success" : "warning"}>
            {isConfirmed ? "Confirmada na fixture" : "Confirmação humana pendente"}
          </Badge>
        </div>
        <dl className="definition-grid">
          <div>
            <dt>ID da entidade</dt>
            <dd>{detail.entity.id}</dd>
          </div>
          <div>
            <dt>Jurisdição</dt>
            <dd>
              {detail.entity.jurisdiction.label} ({detail.entity.jurisdiction.code})
            </dd>
          </div>
          <div>
            <dt>Confirmação</dt>
            <dd>
              {detail.entity.confirmation.confirmedAt === null
                ? "Não confirmada"
                : formatDate(detail.entity.confirmation.confirmedAt)}
            </dd>
          </div>
          <div>
            <dt>Natureza dos dados</dt>
            <dd>Fixture sintética local</dd>
          </div>
        </dl>
      </Card>

      <section className="detail-columns">
        <Card title="Identificadores">
          <dl className="stacked-definition-list">
            {detail.entity.identifiers.map((identifier) => (
              <div key={`${identifier.label}-${identifier.value}`}>
                <dt>{identifier.label}</dt>
                <dd>{identifier.value}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title="Aliases">
          {detail.entity.aliases.length === 0 ? (
            <p className="empty-inline">Nenhum alias informado na fixture.</p>
          ) : (
            <ul className="plain-list">
              {detail.entity.aliases.map((alias) => (
                <li key={alias}>{alias}</li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <Card title="Dados usados na confirmação">
        <p className="boundary-callout">
          Estes fatores descrevem somente a fixture. Não são prova de identidade externa e não
          substituem a decisão humana registrada pelo domínio.
        </p>
        <ul className="plain-list">
          {detail.entity.confirmation.basis.map((basis) => (
            <li key={basis}>{basis}</li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function DeferredHistoryTab({ tab }: { readonly tab: DetailTabId }) {
  if (tab !== "history") return null;
  return (
    <StatePanel kind="unavailable" title="Histórico completo em próxima etapa">
      Somente os históricos factuais estritamente necessários são exibidos nas vistas de Evidence e
      Claim.
    </StatePanel>
  );
}

export function InvestigationDetailPage({
  dataSource = fixtureIntelligenceDataSource,
}: InvestigationDetailPageProps) {
  const { investigationId = "" } = useParams<{ investigationId: string }>();
  const [searchParameters] = useSearchParams();
  const requestedTab = searchParameters.get("tab") ?? "overview";
  const activeTab: DetailTabId = validTabIds.has(requestedTab as DetailTabId)
    ? (requestedTab as DetailTabId)
    : "overview";
  const [loadState, setLoadState] = useState<DetailLoadState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([
      dataSource.getInvestigationDetail(investigationId),
      dataSource.getRecentActivity(),
    ]).then(
      ([detail, activity]) => {
        if (!isCurrent) return;
        setLoadState(
          detail === null
            ? { status: "not-found" }
            : {
                status: "ready",
                detail,
                activity: activity.filter((item) => item.investigationId === investigationId),
              },
        );
      },
      () => {
        if (isCurrent) setLoadState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [dataSource, investigationId, retryVersion]);

  if (loadState.status === "loading") return <DetailLoading />;
  if (loadState.status === "error") {
    return (
      <StatePanel
        actionLabel="Tentar novamente"
        kind="error"
        onAction={() => {
          setLoadState({ status: "loading" });
          setRetryVersion((current) => current + 1);
        }}
        title="Não foi possível carregar a investigação"
      >
        O read adapter sintético falhou. Nenhuma consulta de backend foi realizada.
      </StatePanel>
    );
  }
  if (loadState.status === "not-found") {
    return (
      <StatePanel kind="empty" title="Investigação não encontrada">
        O identificador da URL não corresponde a uma investigação disponível nas fixtures.
        <div className="state-panel__inline-action">
          <Link className="button button--secondary" to="/investigacoes">
            Ver investigações
          </Link>
        </div>
      </StatePanel>
    );
  }

  const { activity, detail } = loadState;
  return (
    <div className="page-stack investigation-detail-page">
      <section className="detail-hero" aria-labelledby="investigation-entity-title">
        <div>
          <p className="eyebrow">{detail.id}</p>
          <h2 id="investigation-entity-title">{detail.entity.legalName}</h2>
          <p>
            {detail.entity.primaryIdentifier.value} · {detail.entity.jurisdiction.label} (
            {detail.entity.jurisdiction.code})
          </p>
        </div>
        <div className="detail-hero__status">
          <Badge tone={getInvestigationStatusTone(detail.lifecycleStatus)}>
            {investigationStatusLabels[detail.lifecycleStatus]}
          </Badge>
          <span>
            Atualizada em <time dateTime={detail.updatedAt}>{formatDate(detail.updatedAt)}</time>
          </span>
        </div>
      </section>

      <nav aria-label="Seções da investigação" className="detail-tabs">
        <div>
          {tabs.map((tab) => (
            <Link
              aria-current={activeTab === tab.id ? "page" : undefined}
              className={activeTab === tab.id ? "detail-tab detail-tab--active" : "detail-tab"}
              key={tab.id}
              to={tab.id === "overview" ? "." : `?tab=${tab.id}`}
            >
              {tab.label}
            </Link>
          ))}
        </div>
      </nav>

      <section aria-labelledby={`detail-tab-${activeTab}`}>
        <h3 className="sr-only" id={`detail-tab-${activeTab}`}>
          {tabs.find((tab) => tab.id === activeTab)?.label}
        </h3>
        {activeTab === "overview" ? (
          <InvestigationOverview activity={activity} detail={detail} />
        ) : null}
        {activeTab === "entity" ? <InvestigationEntity detail={detail} /> : null}
        {activeTab === "evidence" ? (
          <EvidenceCollection
            claims={detail.claims}
            evidence={detail.evidence}
            investigations={[detail]}
            scopedInvestigationId={detail.id}
          />
        ) : null}
        {activeTab === "claims" ? (
          <ClaimsCollection
            claims={detail.claims}
            investigations={[detail]}
            scopedInvestigationId={detail.id}
          />
        ) : null}
        {activeTab === "reviews" ? (
          <ReviewsCollection
            claims={detail.claims}
            investigations={[detail]}
            reviews={detail.factualReviews}
            scopedInvestigationId={detail.id}
          />
        ) : null}
        <DeferredHistoryTab tab={activeTab} />
      </section>
    </div>
  );
}
