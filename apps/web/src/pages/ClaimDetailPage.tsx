import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { ClaimEvidenceList } from "../components/intelligence/ClaimEvidenceList";
import { CollectionLoading } from "../components/intelligence/CollectionPageState";
import {
  ContradictionIndicator,
  SemanticStatusGroup,
} from "../components/intelligence/StatusComponents";
import { Badge, Card, StatePanel } from "../components/ui";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type { ClaimSummary, EvidenceSummary, InvestigationSummary } from "../data/types";
import { claimAssessmentLabels } from "../presentation/investigationPresentation";

type ClaimDetailState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "not-found" }
  | {
      readonly status: "ready";
      readonly claim: ClaimSummary;
      readonly evidence: readonly EvidenceSummary[];
      readonly investigations: readonly InvestigationSummary[];
    };

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function ClaimDetailPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const { claimId = "" } = useParams<{ claimId: string }>();
  const [state, setState] = useState<ClaimDetailState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([
      dataSource.getClaimDetail(claimId),
      dataSource.listEvidence(),
      dataSource.listInvestigations(),
    ]).then(
      ([claim, evidence, investigations]) => {
        if (!isCurrent) return;
        setState(
          claim === null
            ? { status: "not-found" }
            : { status: "ready", claim, evidence, investigations },
        );
      },
      () => {
        if (isCurrent) setState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [claimId, dataSource, retryVersion]);

  if (state.status === "loading") return <CollectionLoading label="Carregando detalhe da Claim" />;
  if (state.status === "error")
    return (
      <StatePanel
        actionLabel="Tentar novamente"
        kind="error"
        onAction={() => {
          setState({ status: "loading" });
          setRetryVersion((current) => current + 1);
        }}
        title="Não foi possível carregar a Claim"
      >
        Os dados sintéticos locais não foram carregados; nenhum backend foi consultado.
      </StatePanel>
    );
  if (state.status === "not-found")
    return (
      <StatePanel kind="empty" title="Claim não encontrada">
        O identificador não corresponde ao modelo de leitura sintético.
        <div className="state-panel__inline-action">
          <Link className="button button--secondary" to="/claims">
            Ver Claims
          </Link>
        </div>
      </StatePanel>
    );

  const investigation = new Map(state.investigations.map((item) => [item.id, item])).get(
    state.claim.investigationId,
  );
  const evidenceById = new Map(state.evidence.map((item) => [item.id, item]));
  return (
    <div className="page-stack detail-record-page">
      <section aria-labelledby="claim-detail-title" className="detail-hero">
        <div>
          <p className="eyebrow">
            {state.claim.id} · versão {state.claim.version}
          </p>
          <h2 id="claim-detail-title">{state.claim.label}</h2>
          <p>{investigation?.entity.legalName ?? state.claim.investigationId}</p>
        </div>
        <div className="detail-hero__status">
          <Badge tone={state.claim.criticality === "CRITICAL" ? "danger" : "neutral"}>
            {state.claim.criticality === "CRITICAL" ? "Crítica" : "Padrão"}
          </Badge>
          <span>{claimAssessmentLabels[state.claim.assessment]}</span>
        </div>
      </section>
      <p className="semantic-boundary-banner semantic-boundary-banner--strong">
        <strong>ELIGIBLE ≠ ADMISSIBLE ≠ ACCEPTED FOR INTERNAL FACTUAL USE</strong>
        <span>
          Cada decisão tem finalidade, escopo e versão próprios. Nenhuma delas torna a Claim
          verdadeira ou apta para crédito.
        </span>
      </p>
      <section className="detail-columns">
        <Card title="Estados semânticos">
          <SemanticStatusGroup
            evidenceUses={state.claim.evidenceUses}
            reviewStatus={state.claim.factualReview.effectiveStatus}
          />
        </Card>
        <Card title="Contradições e qualificações">
          <ContradictionIndicator evidenceUses={state.claim.evidenceUses} />
          <p className="card__summary">
            QUALIFIES adiciona contexto e não funciona como score, suporte ou contradição.
          </p>
        </Card>
      </section>
      <Card title="Base de Evidence da versão exata">
        <ClaimEvidenceList evidenceById={evidenceById} evidenceUses={state.claim.evidenceUses} />
      </Card>
      <Card title="Histórico da Claim">
        <ol className="timeline">
          {state.claim.history.map((item) => (
            <li key={`${String(item.version)}-${item.occurredAt}`}>
              <strong>
                Versão {item.version} · {item.summary}
              </strong>
              <time dateTime={item.occurredAt}>
                {dateFormatter.format(new Date(item.occurredAt))}
              </time>
            </li>
          ))}
        </ol>
      </Card>
      <Link className="text-link" to="/claims">
        Voltar para Claims
      </Link>
    </div>
  );
}
