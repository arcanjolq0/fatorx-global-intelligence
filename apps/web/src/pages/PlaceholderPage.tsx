import type { AppRouteDefinition } from "../app/navigation";
import { Badge, Card, StatePanel } from "../components/ui";

export interface PlaceholderPageProps {
  readonly route: AppRouteDefinition;
}

export function PlaceholderPage({ route }: PlaceholderPageProps) {
  return (
    <div className="page-stack">
      <section className="page-intro" aria-labelledby="page-title">
        <div>
          <h2 id="page-title">Foundation do módulo</h2>
          <p>{route.description}</p>
        </div>
        <Badge tone="info">Foundation</Badge>
      </section>

      <Card className="foundation-placeholder">
        <StatePanel kind="unavailable" title="Módulo ainda não implementado">
          Esta rota valida a arquitetura de navegação e o shell. Dados e ações serão adicionados
          somente através da próxima fronteira de fixtures tipadas, sem antecipar integração com o
          backend.
        </StatePanel>
      </Card>
    </div>
  );
}
