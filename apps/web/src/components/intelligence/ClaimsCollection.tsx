import { useState } from "react";
import type { ChangeEvent } from "react";
import { Link } from "react-router";

import { getClaimDetailPath, getInvestigationDetailPath } from "../../app/navigation";
import type { ClaimSummary, InvestigationSummary } from "../../data/types";
import {
  claimAssessmentLabels,
  factualReviewStatusLabels,
} from "../../presentation/investigationPresentation";
import { Badge, Card, Input, Select, StatePanel, Table } from "../ui";
import type { TableColumn } from "../ui";
import { ClaimStatusStack, ContradictionIndicator, ReviewStatusBadge } from "./StatusComponents";

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
}

export function ClaimsCollection({
  claims,
  investigations,
  scopedInvestigationId,
}: {
  readonly claims: readonly ClaimSummary[];
  readonly investigations: readonly InvestigationSummary[];
  readonly scopedInvestigationId?: string;
}) {
  const [search, setSearch] = useState("");
  const [investigationFilter, setInvestigationFilter] = useState("all");
  const [criticalityFilter, setCriticalityFilter] = useState("all");
  const [reviewFilter, setReviewFilter] = useState("all");
  const investigationById = new Map(investigations.map((item) => [item.id, item]));
  const normalizedSearch = normalize(search);
  const rows = claims.filter((claim) => {
    const investigation = investigationById.get(claim.investigationId);
    const searchable = normalize(
      `${claim.id} ${claim.label} ${investigation?.entity.legalName ?? ""}`,
    );
    return (
      (scopedInvestigationId === undefined || claim.investigationId === scopedInvestigationId) &&
      (investigationFilter === "all" || claim.investigationId === investigationFilter) &&
      (criticalityFilter === "all" || claim.criticality === criticalityFilter) &&
      (reviewFilter === "all" || claim.factualReview.effectiveStatus === reviewFilter) &&
      (normalizedSearch.length === 0 || searchable.includes(normalizedSearch))
    );
  });

  if (claims.length === 0) {
    return (
      <StatePanel kind="empty" title="Nenhuma Claim disponível">
        O modelo de leitura sintético não contém Claims para este escopo.
      </StatePanel>
    );
  }

  const columns: readonly TableColumn<ClaimSummary>[] = [
    {
      id: "claim",
      header: "Claim",
      cell: (claim) => (
        <div className="record-identity">
          <Link to={getClaimDetailPath(claim.id)}>{claim.label}</Link>
          <small>
            {claim.id} · v{claim.version}
          </small>
        </div>
      ),
    },
    {
      id: "context",
      header: "Investigação / entidade",
      mobileLabel: "Contexto",
      cell: (claim) => {
        const investigation = investigationById.get(claim.investigationId);
        return investigation === undefined ? (
          claim.investigationId
        ) : (
          <div className="record-identity">
            <Link to={getInvestigationDetailPath(claim.investigationId)}>
              {investigation.entity.legalName}
            </Link>
            <small>{claim.investigationId}</small>
          </div>
        );
      },
    },
    {
      id: "criticality",
      header: "Criticidade / assessment",
      cell: (claim) => (
        <div className="badge-stack">
          <Badge tone={claim.criticality === "CRITICAL" ? "danger" : "neutral"}>
            {claim.criticality === "CRITICAL" ? "Crítica" : "Padrão"}
          </Badge>
          <span>{claimAssessmentLabels[claim.assessment]}</span>
        </div>
      ),
    },
    {
      id: "roles",
      header: "Evidence por papel",
      cell: (claim) => <ContradictionIndicator evidenceUses={claim.evidenceUses} />,
    },
    {
      id: "semantics",
      header: "Estados semânticos",
      cell: (claim) => (
        <ClaimStatusStack
          evidenceUses={claim.evidenceUses}
          reviewStatus={claim.factualReview.effectiveStatus}
        />
      ),
    },
    {
      id: "attention",
      header: "Atenção",
      cell: (claim) =>
        claim.assessment === "CONFLICTED" || claim.factualReview.effectiveStatus !== "ACCEPTED" ? (
          <ReviewStatusBadge status={claim.factualReview.effectiveStatus} />
        ) : (
          <span className="muted-value">Sem alerta adicional</span>
        ),
    },
  ];

  function handleSearch(event: ChangeEvent<HTMLInputElement>) {
    setSearch(event.target.value);
  }
  function handleInvestigation(event: ChangeEvent<HTMLSelectElement>) {
    setInvestigationFilter(event.target.value);
  }
  function handleCriticality(event: ChangeEvent<HTMLSelectElement>) {
    setCriticalityFilter(event.target.value);
  }
  function handleReview(event: ChangeEvent<HTMLSelectElement>) {
    setReviewFilter(event.target.value);
  }

  return (
    <div className="collection-stack">
      <Card className="collection-filters" title="Filtrar Claims">
        <div className="collection-filter-grid">
          <Input
            label="Busca local"
            onChange={handleSearch}
            placeholder="Claim, ID ou entidade"
            type="search"
            value={search}
          />
          {scopedInvestigationId === undefined ? (
            <Select
              label="Investigação"
              onChange={handleInvestigation}
              options={[
                { label: "Todas as investigações", value: "all" },
                ...investigations.map((item) => ({ label: item.entity.legalName, value: item.id })),
              ]}
              value={investigationFilter}
            />
          ) : null}
          <Select
            label="Criticidade"
            onChange={handleCriticality}
            options={[
              { label: "Todas", value: "all" },
              { label: "Padrão", value: "STANDARD" },
              { label: "Crítica", value: "CRITICAL" },
            ]}
            value={criticalityFilter}
          />
          <Select
            label="Revisão factual"
            onChange={handleReview}
            options={[
              { label: "Todos os estados", value: "all" },
              ...Object.entries(factualReviewStatusLabels).map(([value, label]) => ({
                value,
                label,
              })),
            ]}
            value={reviewFilter}
          />
        </div>
        <p className="filter-result-count" aria-live="polite">
          {rows.length} de {claims.length} Claims
        </p>
      </Card>
      <Card className="collection-table-card">
        {rows.length === 0 ? (
          <StatePanel kind="empty" title="Nenhuma Claim corresponde aos filtros">
            Ajuste a busca, a criticidade ou o estado de revisão factual.
          </StatePanel>
        ) : (
          <Table
            caption="Claims e estados semânticos independentes"
            columns={columns}
            getRowKey={(claim) => claim.id}
            rows={rows}
          />
        )}
      </Card>
    </div>
  );
}
