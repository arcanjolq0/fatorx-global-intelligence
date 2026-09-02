import { ClaimsCollection } from "../components/intelligence/ClaimsCollection";
import { CollectionError, CollectionLoading } from "../components/intelligence/CollectionPageState";
import { Badge } from "../components/ui";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import { useIntelligenceReadModel } from "../hooks/useIntelligenceReadModel";

export function ClaimsPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const { retry, state } = useIntelligenceReadModel(dataSource);
  if (state.status === "loading") return <CollectionLoading label="Carregando Claims" />;
  if (state.status === "error") return <CollectionError onRetry={retry} />;
  return (
    <div className="page-stack">
      <section aria-labelledby="claims-workspace-title" className="page-intro">
        <div>
          <p className="eyebrow">Afirmações estruturadas</p>
          <h2 id="claims-workspace-title">Claims e sua base rastreável</h2>
          <p>
            Compare criticidade, assessment, Evidence vinculada e revisão factual por versão exata.
          </p>
        </div>
        <Badge tone="info">Dados sintéticos</Badge>
      </section>
      <p className="semantic-boundary-banner">
        <strong>Estados independentes:</strong> ELIGIBLE não significa ADMISSIBLE e nenhum deles
        significa ACCEPTED para uso factual interno.
      </p>
      <ClaimsCollection claims={state.claims} investigations={state.investigations} />
    </div>
  );
}
