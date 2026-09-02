import { CollectionError, CollectionLoading } from "../components/intelligence/CollectionPageState";
import { EvidenceCollection } from "../components/intelligence/EvidenceCollection";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import { useIntelligenceReadModel } from "../hooks/useIntelligenceReadModel";

export function EvidenceExplorerPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const { retry, state } = useIntelligenceReadModel(dataSource);
  if (state.status === "loading") return <CollectionLoading label="Carregando Evidence Explorer" />;
  if (state.status === "error") return <CollectionError onRetry={retry} />;
  return (
    <div className="page-stack">
      <p className="semantic-boundary-banner">
        <strong>Leitura sintética:</strong> o campo persistido permanece PENDING. O estado F5.3
        exibido é uma projeção efetiva independente para uso factual interno.
      </p>
      <EvidenceCollection
        claims={state.claims}
        evidence={state.evidence}
        investigations={state.investigations}
      />
    </div>
  );
}
