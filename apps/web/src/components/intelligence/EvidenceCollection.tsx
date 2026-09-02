import { useState } from "react";
import type { ChangeEvent } from "react";
import { Link } from "react-router";

import { getClaimDetailPath, getInvestigationDetailPath } from "../../app/navigation";
import type { ClaimSummary, EvidenceSummary, InvestigationSummary } from "../../data/types";
import {
  evidenceKindLabels,
  evidenceStatusLabels,
} from "../../presentation/investigationPresentation";
import { Badge, Card, Input, Select, StatePanel, Table } from "../ui";
import type { TableColumn } from "../ui";
import { EvidenceStatusBadge } from "./StatusComponents";

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

export interface EvidenceCollectionProps {
  readonly claims: readonly ClaimSummary[];
  readonly evidence: readonly EvidenceSummary[];
  readonly investigations: readonly InvestigationSummary[];
  readonly scopedInvestigationId?: string;
}

export function EvidenceCollection({
  claims,
  evidence,
  investigations,
  scopedInvestigationId,
}: EvidenceCollectionProps) {
  const [search, setSearch] = useState("");
  const [investigationFilter, setInvestigationFilter] = useState("all");
  const [kindFilter, setKindFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const investigationById = new Map(investigations.map((item) => [item.id, item]));
  const claimsByEvidenceId = new Map<string, ClaimSummary[]>();
  for (const claim of claims) {
    for (const evidenceUse of claim.evidenceUses) {
      const linked = claimsByEvidenceId.get(evidenceUse.evidenceId) ?? [];
      linked.push(claim);
      claimsByEvidenceId.set(evidenceUse.evidenceId, linked);
    }
  }

  const normalizedSearch = normalize(search);
  const rows = evidence.filter((item) => {
    const investigation = investigationById.get(item.investigationId);
    const searchable = normalize(
      `${item.friendlyId} ${item.label} ${item.origin.label} ${item.locatorSummary ?? ""} ${investigation?.entity.legalName ?? ""}`,
    );
    return (
      (scopedInvestigationId === undefined || item.investigationId === scopedInvestigationId) &&
      (investigationFilter === "all" || item.investigationId === investigationFilter) &&
      (kindFilter === "all" || item.kind === kindFilter) &&
      (statusFilter === "all" || item.admissibility.status === statusFilter) &&
      (normalizedSearch.length === 0 || searchable.includes(normalizedSearch))
    );
  });

  if (evidence.length === 0) {
    return (
      <StatePanel kind="empty" title="Nenhuma Evidence disponível">
        O modelo de leitura sintético não contém Evidence para este escopo. Nenhuma fonte real foi
        consultada.
      </StatePanel>
    );
  }

  const columns: readonly TableColumn<EvidenceSummary>[] = [
    {
      id: "evidence",
      header: "Evidence",
      cell: (item) => (
        <div className="record-identity">
          <strong>{item.friendlyId}</strong>
          <span>{item.label}</span>
          <small>
            v{item.version} · {evidenceKindLabels[item.kind]}
          </small>
        </div>
      ),
    },
    {
      id: "context",
      header: "Investigação / entidade",
      mobileLabel: "Contexto",
      cell: (item) => {
        const investigation = investigationById.get(item.investigationId);
        return investigation === undefined ? (
          item.investigationId
        ) : (
          <div className="record-identity">
            <Link to={getInvestigationDetailPath(item.investigationId)}>
              {investigation.entity.legalName}
            </Link>
            <small>{item.investigationId}</small>
          </div>
        );
      },
    },
    {
      id: "origin",
      header: "Origem / locator",
      cell: (item) => (
        <div className="record-identity">
          <span>{item.origin.label}</span>
          <small>{item.locatorSummary ?? "Locator não exibido"}</small>
        </div>
      ),
    },
    {
      id: "persisted",
      header: "Persistido",
      cell: (item) => <Badge tone="neutral">{item.persistedAdmissibilityStatus}</Badge>,
    },
    {
      id: "effective",
      header: "F5.3 · efetivo",
      cell: (item) => <EvidenceStatusBadge status={item.admissibility.status} />,
    },
    {
      id: "claims",
      header: "Claims vinculadas",
      cell: (item) => {
        const linkedClaims = claimsByEvidenceId.get(item.id) ?? [];
        return linkedClaims.length === 0 ? (
          <span className="muted-value">Nenhuma</span>
        ) : (
          <ul className="compact-link-list">
            {linkedClaims.map((claim) => (
              <li key={claim.id}>
                <Link to={getClaimDetailPath(claim.id)}>{claim.label}</Link>
              </li>
            ))}
          </ul>
        );
      },
    },
    {
      id: "created",
      header: "Criada em",
      cell: (item) => (
        <time dateTime={item.createdAt}>{dateFormatter.format(new Date(item.createdAt))}</time>
      ),
    },
    {
      id: "history",
      header: "Estado histórico relevante",
      cell: (item) => {
        const latestHistory = item.history[item.history.length - 1];
        return latestHistory === undefined ? (
          <span className="muted-value">Sem evento resumido</span>
        ) : (
          <div className="record-identity">
            <span>{latestHistory.summary}</span>
            <small>
              <time dateTime={latestHistory.occurredAt}>
                {dateFormatter.format(new Date(latestHistory.occurredAt))}
              </time>
            </small>
          </div>
        );
      },
    },
  ];

  function handleSearch(event: ChangeEvent<HTMLInputElement>) {
    setSearch(event.target.value);
  }
  function handleInvestigation(event: ChangeEvent<HTMLSelectElement>) {
    setInvestigationFilter(event.target.value);
  }
  function handleKind(event: ChangeEvent<HTMLSelectElement>) {
    setKindFilter(event.target.value);
  }
  function handleStatus(event: ChangeEvent<HTMLSelectElement>) {
    setStatusFilter(event.target.value);
  }

  return (
    <div className="collection-stack">
      <Card className="collection-filters" title="Filtrar Evidence">
        <div className="collection-filter-grid">
          <Input
            label="Busca local"
            onChange={handleSearch}
            placeholder="ID, título, origem ou locator"
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
            label="Tipo"
            onChange={handleKind}
            options={[
              { label: "Todos os tipos", value: "all" },
              ...Object.entries(evidenceKindLabels).map(([value, label]) => ({ value, label })),
            ]}
            value={kindFilter}
          />
          <Select
            label="Admissibilidade efetiva"
            onChange={handleStatus}
            options={[
              { label: "Todos os estados", value: "all" },
              ...Object.entries(evidenceStatusLabels).map(([value, label]) => ({ value, label })),
            ]}
            value={statusFilter}
          />
        </div>
        <p className="filter-result-count" aria-live="polite">
          {rows.length} de {evidence.length} itens de Evidence
        </p>
      </Card>
      <Card className="collection-table-card">
        {rows.length === 0 ? (
          <StatePanel kind="empty" title="Nenhuma Evidence corresponde aos filtros">
            Ajuste a busca, o tipo ou a admissibilidade efetiva. Os dados continuam locais e
            sintéticos.
          </StatePanel>
        ) : (
          <Table
            caption="Evidence disponível no modelo de leitura sintético"
            columns={columns}
            getRowKey={(item) => item.id}
            rows={rows}
          />
        )}
      </Card>
    </div>
  );
}
