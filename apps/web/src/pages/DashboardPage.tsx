import { useEffect, useState } from "react";
import { Link } from "react-router";

import { StatCard } from "../components/intelligence/StatCard";
import { Timeline } from "../components/intelligence/Timeline";
import { Badge, Card, Skeleton, StatePanel } from "../components/ui";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type {
  ActivityItem,
  ClaimSummary,
  DashboardSummary,
  EffectiveEvidenceAdmissibilityStatus,
  EvidenceSummary,
  InvestigationSummary,
} from "../data/types";
import {
  evidenceStatusLabels,
  factualReviewStatusLabels,
  getEvidenceStatusTone,
  getInvestigationStatusTone,
  getReviewStatusTone,
  investigationStatusLabels,
} from "../presentation/investigationPresentation";
import { getClaimDetailPath, getInvestigationDetailPath } from "../app/navigation";

type DashboardState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | {
      readonly status: "ready";
      readonly activity: readonly ActivityItem[];
      readonly claims: readonly ClaimSummary[];
      readonly evidence: readonly EvidenceSummary[];
      readonly investigations: readonly InvestigationSummary[];
      readonly summary: DashboardSummary;
    };

const evidenceStates: readonly EffectiveEvidenceAdmissibilityStatus[] = [
  "ADMISSIBLE",
  "PENDING",
  "RESTRICTED",
  "EXPIRED",
  "REVOKED",
  "REJECTED",
];

function DashboardLoading() {
  return (
    <div
      aria-busy="true"
      aria-label="Carregando Visão Geral"
      className="dashboard-loading"
      role="status"
    >
      <div className="dashboard-kpis">
        {[0, 1, 2, 3].map((item) => (
          <Skeleton height="9rem" key={item} />
        ))}
      </div>
      <div className="dashboard-grid">
        <Skeleton height="20rem" />
        <Skeleton height="20rem" />
      </div>
    </div>
  );
}

export function DashboardPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const [state, setState] = useState<DashboardState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([
      dataSource.getDashboardSummary(),
      dataSource.listInvestigations(),
      dataSource.listEvidence(),
      dataSource.listClaims(),
      dataSource.getRecentActivity(),
    ]).then(
      ([summary, investigations, evidence, claims, activity]) => {
        if (isCurrent) {
          setState({ status: "ready", summary, investigations, evidence, claims, activity });
        }
      },
      () => {
        if (isCurrent) setState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [dataSource, retryVersion]);

  if (state.status === "loading") return <DashboardLoading />;
  if (state.status === "error") {
    return (
      <StatePanel
        actionLabel="Tentar novamente"
        kind="error"
        onAction={() => {
          setState({ status: "loading" });
          setRetryVersion((current) => current + 1);
        }}
        title="Não foi possível carregar a Visão Geral"
      >
        O adaptador de fixtures falhou. Nenhum serviço externo foi consultado.
      </StatePanel>
    );
  }

  const attentionClaims = state.claims.filter(
    (claim) =>
      claim.assessment === "CONFLICTED" || claim.factualReview.effectiveStatus !== "ACCEPTED",
  );
  const recentInvestigations = state.investigations.toSorted((left, right) =>
    right.updatedAt.localeCompare(left.updatedAt),
  );
  const contradictions = state.claims.filter((claim) => claim.assessment === "CONFLICTED");
  const investigationById = new Map(state.investigations.map((item) => [item.id, item]));
  const evidenceCounts = new Map(
    evidenceStates.map((status) => [
      status,
      state.evidence.filter((item) => item.admissibility.status === status).length,
    ]),
  );
  const jurisdictionCounts = new Map<string, { label: string; count: number }>();
  for (const investigation of state.investigations) {
    const jurisdiction = investigation.entity.jurisdiction;
    const current = jurisdictionCounts.get(jurisdiction.code);
    jurisdictionCounts.set(jurisdiction.code, {
      label: `${jurisdiction.label} (${jurisdiction.code})`,
      count: (current?.count ?? 0) + 1,
    });
  }

  return (
    <div className="page-stack dashboard-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">Panorama operacional</p>
          <h2>Visão consolidada do workspace</h2>
          <p>
            Indicadores derivados exclusivamente das fixtures tipadas, sem score, fonte real ou
            inferência de risco.
          </p>
        </div>
        <Badge tone="info">Dados sintéticos controlados</Badge>
      </section>

      <section aria-label="Indicadores do workspace" className="dashboard-kpis">
        <StatCard
          detail={`${state.summary.activeInvestigations.toLocaleString("pt-BR")} em fluxo na fixture`}
          icon="investigations"
          label="Investigações"
          value={state.summary.totalInvestigations}
        />
        <StatCard
          detail="Evidence canônica no cenário local"
          icon="evidence"
          label="Evidence"
          tone="success"
          value={state.summary.evidenceItems}
        />
        <StatCard
          detail="Afirmações estruturadas"
          icon="claims"
          label="Claims"
          tone="violet"
          value={state.summary.claims}
        />
        <StatCard
          detail="Decisões F5.4 ainda pendentes"
          icon="reviews"
          label="Revisões pendentes"
          tone="warning"
          value={state.summary.pendingReviews}
        />
      </section>

      {state.investigations.length === 0 ? (
        <StatePanel kind="empty" title="Nenhum dado no cenário atual">
          O dashboard está pronto para receber um modelo de leitura, mas a fixture selecionada está
          vazia.
        </StatePanel>
      ) : (
        <>
          <section className="dashboard-grid dashboard-grid--primary">
            <Card title="Investigações recentes">
              <ul className="data-list">
                {recentInvestigations.slice(0, 4).map((investigation) => (
                  <li key={investigation.id}>
                    <span>
                      <Link className="text-link" to={getInvestigationDetailPath(investigation.id)}>
                        <strong>{investigation.entity.legalName}</strong>
                      </Link>
                      <small>{investigation.entity.jurisdiction.label}</small>
                    </span>
                    <Badge tone={getInvestigationStatusTone(investigation.lifecycleStatus)}>
                      {investigationStatusLabels[investigation.lifecycleStatus]}
                    </Badge>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Claims que exigem atenção">
              {attentionClaims.length === 0 ? (
                <p className="empty-inline">Nenhuma Claim exige atenção na fixture atual.</p>
              ) : (
                <ul className="data-list">
                  {attentionClaims.slice(0, 4).map((claim) => (
                    <li key={claim.id}>
                      <span>
                        <Link className="text-link" to={getClaimDetailPath(claim.id)}>
                          <strong>{claim.label}</strong>
                        </Link>
                        <small>
                          {investigationById.get(claim.investigationId)?.entity.legalName ??
                            claim.investigationId}
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

          <section className="dashboard-grid">
            <Card title="Estado efetivo da Evidence">
              <div className="distribution-list">
                {evidenceStates.map((status) => {
                  const count = evidenceCounts.get(status) ?? 0;
                  return (
                    <div className="distribution-row" key={status}>
                      <span>
                        <Badge tone={getEvidenceStatusTone(status)}>
                          {evidenceStatusLabels[status]}
                        </Badge>
                        <strong>{count}</strong>
                      </span>
                      <progress
                        aria-label={`${evidenceStatusLabels[status]}: ${count.toLocaleString("pt-BR")}`}
                        max={Math.max(state.evidence.length, 1)}
                        value={count}
                      />
                    </div>
                  );
                })}
              </div>
              <p className="card__summary">
                Projeção efetiva F5.3; o campo persistido continua PENDING em toda Evidence.
              </p>
            </Card>

            <Card title="Distribuição por jurisdição">
              <div className="distribution-list">
                {[...jurisdictionCounts.entries()].map(([code, item]) => (
                  <div className="distribution-row" key={code}>
                    <span>
                      <span>{item.label}</span>
                      <strong>{item.count}</strong>
                    </span>
                    <progress
                      aria-label={`${item.label}: ${item.count.toLocaleString("pt-BR")}`}
                      max={state.investigations.length}
                      value={item.count}
                    />
                  </div>
                ))}
              </div>
              <p className="card__summary">Cobertura apenas do cenário sintético local.</p>
            </Card>
          </section>

          <section className="dashboard-grid">
            <Card title="Atividade recente">
              <Timeline
                entries={state.activity.slice(0, 5).map((item) => ({
                  id: item.id,
                  occurredAt: item.occurredAt,
                  title: item.summary,
                  meta: investigationById.get(item.investigationId)?.entity.legalName,
                }))}
              />
            </Card>
            <Card title="Contradições abertas">
              {contradictions.length === 0 ? (
                <p className="empty-inline">Nenhuma contradição explícita na fixture atual.</p>
              ) : (
                <ul className="contradiction-list">
                  {contradictions.map((claim) => (
                    <li key={claim.id}>
                      <Link className="text-link" to={getClaimDetailPath(claim.id)}>
                        <strong>{claim.label}</strong>
                      </Link>
                      <span>
                        {claim.evidenceUses.filter((use) => use.role === "CONTRADICTS").length}
                        {" vínculo(s) contraditório(s) explícito(s); isso não torna a Claim falsa."}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
