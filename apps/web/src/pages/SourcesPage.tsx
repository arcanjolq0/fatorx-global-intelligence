import { useEffect, useState } from "react";

import { CollectionError, CollectionLoading } from "../components/intelligence/CollectionPageState";
import { Badge, Card, Table } from "../components/ui";
import type { TableColumn } from "../components/ui";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type { ControlledSourceSummary } from "../data/types";
import {
  controlledSourceKindLabels,
  controlledSourceStatusLabels,
} from "../presentation/governancePresentation";

type SourcesState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "ready"; readonly sources: readonly ControlledSourceSummary[] };

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

const columns: readonly TableColumn<ControlledSourceSummary>[] = [
  {
    id: "source",
    header: "Canal controlado",
    cell: (source) => (
      <span className="record-identity">
        <strong>{source.label}</strong>
        <small>{source.id}</small>
      </span>
    ),
  },
  {
    id: "type",
    header: "Tipo",
    cell: (source) => controlledSourceKindLabels[source.kind],
  },
  {
    id: "coverage",
    header: "Cobertura da fixture",
    cell: (source) => source.coverage.map((item) => `${item.label} (${item.code})`).join(", "),
  },
  {
    id: "status",
    header: "Estado",
    cell: (source) => (
      <Badge tone={source.status === "CONTROLLED_TEST_FIXTURE" ? "info" : "warning"}>
        {controlledSourceStatusLabels[source.status]}
      </Badge>
    ),
  },
  {
    id: "limitations",
    header: "Limitações",
    cell: (source) => (
      <ul className="compact-limitations">
        {source.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    ),
  },
  {
    id: "validated",
    header: "Validada na fixture",
    cell: (source) => (
      <time dateTime={source.validatedAt}>
        {dateFormatter.format(new Date(source.validatedAt))}
      </time>
    ),
  },
];

export function SourcesPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const [state, setState] = useState<SourcesState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);

  useEffect(() => {
    let isCurrent = true;
    void dataSource.listControlledSources().then(
      (sources) => {
        if (isCurrent) setState({ status: "ready", sources });
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
    return <CollectionLoading label="Carregando fontes controladas" />;
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

  return (
    <div className="page-stack governance-page">
      <section className="page-intro">
        <div>
          <p className="eyebrow">Catálogo de demonstração</p>
          <h2>Fontes e canais controlados</h2>
          <p>
            Inventário somente leitura dos canais sintéticos usados pelas fixtures da interface.
          </p>
        </div>
      </section>
      <p className="semantic-boundary-banner semantic-boundary-banner--strong">
        <strong>Nenhuma fonte real está habilitada ou aprovada.</strong>
        Estes registros são simulados para TEST, sem acesso, licença, atualização ou cobertura
        produtiva. Eles não constituem o catálogo G6.
      </p>
      <Card className="governance-table-card">
        <Table
          caption="Fontes sintéticas controladas"
          columns={columns}
          emptyDescription="Nenhum canal de fixture está configurado neste cenário. Isso não aciona descoberta externa."
          emptyTitle="Nenhuma fonte controlada disponível"
          getRowKey={(source) => source.id}
          rows={state.sources}
        />
      </Card>
    </div>
  );
}
