import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import { CollectionError, CollectionLoading } from "../components/intelligence/CollectionPageState";
import { Badge, Card, Input, Select, Table } from "../components/ui";
import type { TableColumn } from "../components/ui";
import { getInvestigationDetailPath } from "../app/navigation";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type { AuditEventCategory, AuditEventSummary, InvestigationSummary } from "../data/types";
import {
  auditCategoryLabels,
  auditResultLabels,
  getAuditResultTone,
} from "../presentation/governancePresentation";

type AuditState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | {
      readonly status: "ready";
      readonly events: readonly AuditEventSummary[];
      readonly investigations: readonly InvestigationSummary[];
    };

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

function normalize(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR");
}

export function AuditPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const [state, setState] = useState<AuditState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<AuditEventCategory | "ALL">("ALL");
  const [action, setAction] = useState("ALL");
  const [investigationId, setInvestigationId] = useState("ALL");

  useEffect(() => {
    let isCurrent = true;
    void Promise.all([dataSource.listAuditEvents(), dataSource.listInvestigations()]).then(
      ([events, investigations]) => {
        if (isCurrent) setState({ status: "ready", events, investigations });
      },
      () => {
        if (isCurrent) setState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [dataSource, retryVersion]);

  const filteredEvents = useMemo(() => {
    if (state.status !== "ready") return [];
    const query = normalize(search.trim());
    return state.events.filter((event) => {
      const searchable = normalize(
        [
          event.action,
          event.objectReference,
          event.actor?.displayName ?? "",
          event.investigationId,
        ].join(" "),
      );
      return (
        (query.length === 0 || searchable.includes(query)) &&
        (category === "ALL" || event.category === category) &&
        (action === "ALL" || event.action === action) &&
        (investigationId === "ALL" || event.investigationId === investigationId)
      );
    });
  }, [action, category, investigationId, search, state]);

  if (state.status === "loading") return <CollectionLoading label="Carregando auditoria" />;
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

  const investigationById = new Map(state.investigations.map((item) => [item.id, item]));
  const columns: readonly TableColumn<AuditEventSummary>[] = [
    {
      id: "timestamp",
      header: "Data e hora",
      cell: (event) => (
        <time dateTime={event.occurredAt}>{dateFormatter.format(new Date(event.occurredAt))}</time>
      ),
    },
    {
      id: "category",
      header: "Categoria",
      cell: (event) => <Badge tone="neutral">{auditCategoryLabels[event.category]}</Badge>,
    },
    { id: "action", header: "Ação", cell: (event) => event.action },
    {
      id: "object",
      header: "Objeto",
      cell: (event) => <span className="audit-object">{event.objectReference}</span>,
    },
    {
      id: "actor",
      header: "Ator",
      cell: (event) => event.actor?.displayName ?? "Não informado na fixture",
    },
    {
      id: "investigation",
      header: "Investigação",
      cell: (event) => (
        <Link className="text-link" to={getInvestigationDetailPath(event.investigationId)}>
          {investigationById.get(event.investigationId)?.entity.legalName ?? event.investigationId}
        </Link>
      ),
    },
    {
      id: "result",
      header: "Resultado",
      cell: (event) => (
        <Badge tone={getAuditResultTone(event.result)}>{auditResultLabels[event.result]}</Badge>
      ),
    },
  ];

  return (
    <div className="page-stack governance-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">Trilha somente leitura</p>
          <h2>Eventos relevantes do workspace</h2>
          <p>Projeção sintética reduzida a metadados seguros e úteis para supervisão.</p>
        </div>
        <Badge tone="neutral">Mock local · read-only</Badge>
      </section>
      <p className="semantic-boundary-banner">
        <strong>Limite de auditoria:</strong> esta tela não consulta eventos persistidos e não expõe
        conteúdo documental, dados pessoais, credenciais ou corpos brutos de mensagens.
      </p>
      <Card className="collection-filters">
        <div className="audit-filter-grid">
          <Input
            label="Buscar eventos"
            onChange={(event) => {
              setSearch(event.currentTarget.value);
            }}
            placeholder="Ação, objeto, ator ou investigação"
            type="search"
            value={search}
          />
          <Select
            label="Categoria"
            onChange={(event) => {
              setCategory(event.currentTarget.value as AuditEventCategory | "ALL");
            }}
            options={[
              { label: "Todas as categorias", value: "ALL" },
              ...Object.entries(auditCategoryLabels).map(([value, label]) => ({ value, label })),
            ]}
            value={category}
          />
          <Select
            label="Ação"
            onChange={(event) => {
              setAction(event.currentTarget.value);
            }}
            options={[
              { label: "Todas as ações", value: "ALL" },
              ...[...new Set(state.events.map((event) => event.action))].map((value) => ({
                label: value,
                value,
              })),
            ]}
            value={action}
          />
          <Select
            label="Investigação"
            onChange={(event) => {
              setInvestigationId(event.currentTarget.value);
            }}
            options={[
              { label: "Todas as investigações", value: "ALL" },
              ...state.investigations.map((investigation) => ({
                label: investigation.entity.legalName,
                value: investigation.id,
              })),
            ]}
            value={investigationId}
          />
        </div>
        <p aria-live="polite" className="filter-result-count">
          {filteredEvents.length} de {state.events.length} eventos
        </p>
      </Card>
      <Card className="governance-table-card audit-table-card">
        <Table
          caption="Eventos de auditoria sintéticos"
          columns={columns}
          emptyDescription="Ajuste os filtros locais para encontrar outro evento da fixture."
          emptyTitle="Nenhum evento corresponde aos filtros"
          getRowKey={(event) => event.id}
          rows={filteredEvents}
        />
      </Card>
    </div>
  );
}
