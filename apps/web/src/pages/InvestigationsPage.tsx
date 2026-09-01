import { useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { Link } from "react-router";

import { getInvestigationDetailPath } from "../app/navigation";
import { Badge } from "../components/ui/Badge";
import { Card } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Skeleton } from "../components/ui/Skeleton";
import { StatePanel } from "../components/ui/StatePanel";
import { Table } from "../components/ui/Table";
import type { TableColumn } from "../components/ui/Table";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type { InvestigationLifecycleStatus, InvestigationSummary } from "../data/types";

interface InvestigationsPageProps {
  readonly dataSource?: IntelligenceDataSource;
}

type InvestigationsLoadState =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly investigations: readonly InvestigationSummary[] }
  | { readonly status: "error" };

const statusLabels: Readonly<Record<InvestigationLifecycleStatus, string>> = {
  CREATED: "Criada",
  IDENTIFYING: "Identificando",
  WAITING_FOR_ENTITY_CONFIRMATION: "Aguardando entidade",
  PLANNING: "Planejamento",
  COLLECTING: "Coleta",
  NORMALIZING: "Normalização",
  VERIFYING: "Verificação",
  ANALYZING: "Análise",
  WAITING_FOR_REVIEW: "Aguardando revisão",
  COMPLETED: "Concluída",
  PARTIALLY_COMPLETED: "Parcialmente concluída",
  FAILED: "Falhou",
  CANCELLED: "Cancelada",
};

const statusOptions = [
  { value: "all", label: "Todos os estados" },
  ...Object.entries(statusLabels).map(([value, label]) => ({ value, label })),
];

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

function getStatusTone(
  status: InvestigationLifecycleStatus,
): "neutral" | "info" | "success" | "warning" | "danger" {
  if (status === "COMPLETED") {
    return "success";
  }
  if (status === "FAILED" || status === "CANCELLED") {
    return "danger";
  }
  if (status === "WAITING_FOR_ENTITY_CONFIRMATION" || status === "WAITING_FOR_REVIEW") {
    return "warning";
  }
  if (status === "CREATED") {
    return "neutral";
  }
  return "info";
}

function normalizeSearchValue(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
}

function formatPendingCount(count: number, singular: string, plural: string): string {
  return `${count.toLocaleString("pt-BR")} ${count === 1 ? singular : plural}`;
}

const investigationColumns: readonly TableColumn<InvestigationSummary>[] = [
  {
    id: "entity",
    header: "Entidade",
    cell: (investigation) => (
      <div className="investigation-entity">
        <Link to={getInvestigationDetailPath(investigation.id)}>
          {investigation.entity.legalName}
        </Link>
        <small>{investigation.id}</small>
      </div>
    ),
  },
  {
    id: "identifier",
    header: "Identificador principal",
    mobileLabel: "Identificador",
    cell: (investigation) => (
      <div className="identifier-value">
        <span>{investigation.entity.primaryIdentifier.value}</span>
        <small>{investigation.entity.primaryIdentifier.label}</small>
      </div>
    ),
  },
  {
    id: "jurisdiction",
    header: "Jurisdição",
    cell: (investigation) => (
      <span>
        {investigation.entity.jurisdiction.label} ({investigation.entity.jurisdiction.code})
      </span>
    ),
  },
  {
    id: "status",
    header: "Estado",
    cell: (investigation) => (
      <Badge tone={getStatusTone(investigation.lifecycleStatus)}>
        {statusLabels[investigation.lifecycleStatus]}
      </Badge>
    ),
  },
  {
    id: "updatedAt",
    header: "Última atualização",
    mobileLabel: "Atualização",
    cell: (investigation) => (
      <time dateTime={investigation.updatedAt}>
        {dateFormatter.format(new Date(investigation.updatedAt))}
      </time>
    ),
  },
  {
    id: "evidence",
    header: "Evidências",
    align: "right",
    cell: (investigation) => investigation.evidenceCount.toLocaleString("pt-BR"),
  },
  {
    id: "pending",
    header: "Pendências",
    cell: (investigation) =>
      investigation.pendingClaimCount === 0 && investigation.pendingReviewCount === 0 ? (
        <span className="muted-value">Sem pendências</span>
      ) : (
        <span className="pending-counts">
          <span>{formatPendingCount(investigation.pendingClaimCount, "claim", "claims")}</span>
          <span>{formatPendingCount(investigation.pendingReviewCount, "revisão", "revisões")}</span>
        </span>
      ),
  },
];

export function InvestigationsPage({
  dataSource = fixtureIntelligenceDataSource,
}: InvestigationsPageProps) {
  const [loadState, setLoadState] = useState<InvestigationsLoadState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<InvestigationLifecycleStatus | "all">("all");

  useEffect(() => {
    let isCurrent = true;

    void dataSource.listInvestigations().then(
      (investigations) => {
        if (isCurrent) {
          setLoadState({ status: "ready", investigations });
        }
      },
      () => {
        if (isCurrent) {
          setLoadState({ status: "error" });
        }
      },
    );

    return () => {
      isCurrent = false;
    };
  }, [dataSource, retryVersion]);

  const normalizedSearch = normalizeSearchValue(search);
  const filteredInvestigations =
    loadState.status === "ready"
      ? loadState.investigations.filter((investigation) => {
          const matchesStatus =
            statusFilter === "all" || investigation.lifecycleStatus === statusFilter;
          const searchableValue = normalizeSearchValue(
            [
              investigation.entity.legalName,
              investigation.entity.primaryIdentifier.value,
              investigation.entity.jurisdiction.label,
              investigation.entity.jurisdiction.code,
            ].join(" "),
          );
          return matchesStatus && searchableValue.includes(normalizedSearch);
        })
      : [];

  const hasActiveFilters = search.trim() !== "" || statusFilter !== "all";

  return (
    <div className="page-stack investigations-page">
      <section className="page-intro" aria-labelledby="investigations-content-title">
        <div>
          <h2 id="investigations-content-title">Workspace de investigações</h2>
          <p>
            Read models sintéticos demonstram a navegação sem representar integração com backend,
            fonte real ou dado produtivo.
          </p>
        </div>
        <Badge tone="info">Dados sintéticos</Badge>
      </section>

      <Card className="investigation-filters">
        <div className="investigation-filters__fields">
          <Input
            disabled={loadState.status !== "ready"}
            label="Buscar investigações"
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              setSearch(event.target.value);
            }}
            placeholder="Entidade, identificador ou jurisdição"
            type="search"
            value={search}
          />
          <Select
            disabled={loadState.status !== "ready"}
            label="Filtrar por estado"
            onChange={(event: ChangeEvent<HTMLSelectElement>) => {
              setStatusFilter(event.target.value as InvestigationLifecycleStatus | "all");
            }}
            options={statusOptions}
            value={statusFilter}
          />
        </div>
        <p aria-live="polite" className="investigation-results-count">
          {loadState.status === "ready"
            ? `${filteredInvestigations.length.toLocaleString("pt-BR")} de ${loadState.investigations.length.toLocaleString("pt-BR")} investigações`
            : "Carregando investigações"}
        </p>
      </Card>

      <Card className="investigations-list-card">
        {loadState.status === "loading" ? (
          <div
            aria-busy="true"
            aria-label="Carregando lista de investigações"
            className="investigation-loading"
            role="status"
          >
            <Skeleton height="1rem" width="38%" />
            <Skeleton height="4.5rem" width="100%" />
            <Skeleton height="4.5rem" width="100%" />
            <Skeleton height="4.5rem" width="100%" />
          </div>
        ) : null}

        {loadState.status === "error" ? (
          <StatePanel
            actionLabel="Tentar novamente"
            kind="error"
            onAction={() => {
              setLoadState({ status: "loading" });
              setRetryVersion((current) => current + 1);
            }}
            title="Não foi possível carregar as investigações"
          >
            O adapter de demonstração falhou. Nenhuma chamada de rede foi realizada.
          </StatePanel>
        ) : null}

        {loadState.status === "ready" ? (
          <Table
            caption="Investigações sintéticas"
            columns={investigationColumns}
            emptyDescription={
              hasActiveFilters
                ? "Ajuste a busca ou o filtro para visualizar outros resultados."
                : "O cenário atual não contém investigações."
            }
            emptyTitle={
              hasActiveFilters
                ? "Nenhuma investigação corresponde aos filtros"
                : "Nenhuma investigação disponível"
            }
            getRowKey={(investigation) => investigation.id}
            rows={filteredInvestigations}
          />
        ) : null}
      </Card>
    </div>
  );
}
