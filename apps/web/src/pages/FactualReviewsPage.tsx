import { CollectionError, CollectionLoading } from "../components/intelligence/CollectionPageState";
import { ReviewsCollection } from "../components/intelligence/ReviewsCollection";
import { Badge } from "../components/ui";
import type { IntelligenceDataSource } from "../data/IntelligenceDataSource";
import { fixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import { useIntelligenceReadModel } from "../hooks/useIntelligenceReadModel";

export function FactualReviewsPage({
  dataSource = fixtureIntelligenceDataSource,
}: {
  readonly dataSource?: IntelligenceDataSource;
}) {
  const { retry, state } = useIntelligenceReadModel(dataSource);
  if (state.status === "loading") return <CollectionLoading label="Carregando revisões factuais" />;
  if (state.status === "error") return <CollectionError onRetry={retry} />;
  return (
    <div className="page-stack">
      <section aria-labelledby="reviews-queue-title" className="page-intro">
        <div>
          <p className="eyebrow">Decisão humana interna</p>
          <h2 id="reviews-queue-title">Fila de revisões factuais</h2>
          <p>
            Acompanhe decisões e invalidações F5.4 sem confundir aceite interno com verdade ou
            reportabilidade.
          </p>
        </div>
        <Badge tone="neutral">Somente leitura</Badge>
      </section>
      <p className="semantic-boundary-banner">
        <strong>Fila somente leitura:</strong> decisões F5.4 se aplicam a uma versão exata da Claim
        e não tornam a afirmação verdadeira, reportável ou apta para crédito.
      </p>
      <ReviewsCollection
        claims={state.claims}
        investigations={state.investigations}
        reviews={state.reviews}
      />
    </div>
  );
}
