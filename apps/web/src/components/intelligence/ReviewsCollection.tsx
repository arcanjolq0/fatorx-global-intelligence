import { useState } from "react";
import type { ChangeEvent } from "react";
import { Link } from "react-router";

import { getInvestigationDetailPath, getReviewDetailPath } from "../../app/navigation";
import type { ClaimReviewSummary, ClaimSummary, InvestigationSummary } from "../../data/types";
import { factualReviewStatusLabels } from "../../presentation/investigationPresentation";
import { Card, Input, Select, StatePanel, Table } from "../ui";
import type { TableColumn } from "../ui";
import { ContradictionIndicator, ReviewStatusBadge } from "./StatusComponents";

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
}

export function ReviewsCollection({
  claims,
  investigations,
  reviews,
  scopedInvestigationId,
}: {
  readonly claims: readonly ClaimSummary[];
  readonly investigations: readonly InvestigationSummary[];
  readonly reviews: readonly ClaimReviewSummary[];
  readonly scopedInvestigationId?: string;
}) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const claimById = new Map(claims.map((claim) => [claim.id, claim]));
  const investigationById = new Map(investigations.map((item) => [item.id, item]));
  const normalizedSearch = normalize(search);
  const rows = reviews.filter((review) => {
    const claim = claimById.get(review.claimId);
    const investigation = investigationById.get(review.investigationId);
    return (
      (scopedInvestigationId === undefined || review.investigationId === scopedInvestigationId) &&
      (statusFilter === "all" || review.effectiveStatus === statusFilter) &&
      (normalizedSearch.length === 0 ||
        normalize(
          `${review.id} ${claim?.label ?? ""} ${investigation?.entity.legalName ?? ""}`,
        ).includes(normalizedSearch))
    );
  });

  if (reviews.length === 0) {
    return (
      <StatePanel kind="empty" title="Nenhuma revisão factual disponível">
        O read model sintético não contém decisões F5.4 para este escopo.
      </StatePanel>
    );
  }

  const columns: readonly TableColumn<ClaimReviewSummary>[] = [
    {
      id: "claim",
      header: "Claim / versão",
      cell: (review) => {
        const claim = claimById.get(review.claimId);
        return (
          <div className="record-identity">
            <Link to={getReviewDetailPath(review.id)}>{claim?.label ?? review.claimId}</Link>
            <small>
              {review.claimId} · v{review.claimVersion}
            </small>
          </div>
        );
      },
    },
    {
      id: "context",
      header: "Investigação / entidade",
      mobileLabel: "Contexto",
      cell: (review) => {
        const investigation = investigationById.get(review.investigationId);
        return investigation === undefined ? (
          review.investigationId
        ) : (
          <div className="record-identity">
            <Link to={getInvestigationDetailPath(review.investigationId)}>
              {investigation.entity.legalName}
            </Link>
            <small>{review.investigationId}</small>
          </div>
        );
      },
    },
    {
      id: "status",
      header: "Estado atual",
      cell: (review) => <ReviewStatusBadge status={review.effectiveStatus} />,
    },
    {
      id: "evidence",
      header: "Evidence / contradições",
      cell: (review) => {
        const claim = claimById.get(review.claimId);
        return claim === undefined ? (
          <span className="muted-value">Base indisponível</span>
        ) : (
          <ContradictionIndicator evidenceUses={claim.evidenceUses} />
        );
      },
    },
    {
      id: "reviewer",
      header: "Revisor",
      cell: (review) =>
        review.reviewer?.displayName ?? <span className="muted-value">Não atribuído</span>,
    },
    {
      id: "decision",
      header: "Decisão / data",
      cell: (review) => (
        <div className="record-identity">
          <span>
            {review.decisionOutcome === null
              ? "Sem decisão"
              : factualReviewStatusLabels[review.effectiveStatus]}
          </span>
          <small>
            {review.reviewedAt === null
              ? "Ainda não decidida"
              : dateFormatter.format(new Date(review.reviewedAt))}
          </small>
        </div>
      ),
    },
  ];

  function handleSearch(event: ChangeEvent<HTMLInputElement>) {
    setSearch(event.target.value);
  }
  function handleStatus(event: ChangeEvent<HTMLSelectElement>) {
    setStatusFilter(event.target.value);
  }

  return (
    <div className="collection-stack">
      <Card className="collection-filters" title="Filtrar revisões">
        <div className="collection-filter-grid collection-filter-grid--compact">
          <Input
            label="Busca local"
            onChange={handleSearch}
            placeholder="Claim, revisão ou entidade"
            type="search"
            value={search}
          />
          <Select
            label="Estado atual"
            onChange={handleStatus}
            options={[
              { label: "Todos os estados", value: "all" },
              ...Object.entries(factualReviewStatusLabels).map(([value, label]) => ({
                value,
                label,
              })),
            ]}
            value={statusFilter}
          />
        </div>
        <p className="filter-result-count" aria-live="polite">
          {rows.length} de {reviews.length} revisão(ões)
        </p>
      </Card>
      <Card className="collection-table-card">
        {rows.length === 0 ? (
          <StatePanel kind="empty" title="Nenhuma revisão corresponde aos filtros">
            Ajuste a busca ou o estado atual. A fila é somente leitura.
          </StatePanel>
        ) : (
          <Table
            caption="Fila de revisões factuais somente leitura"
            columns={columns}
            getRowKey={(review) => review.id}
            rows={rows}
          />
        )}
      </Card>
    </div>
  );
}
