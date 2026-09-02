import { Link } from "react-router";

import { Badge, Card } from "../components/ui";

export function EntitiesPage() {
  return (
    <div className="page-stack entities-page">
      <section aria-labelledby="entities-title" className="page-intro">
        <div>
          <p className="eyebrow">Identidade no contexto investigativo</p>
          <h2 id="entities-title">Entidades vinculadas às investigações</h2>
          <p>
            A identidade é apresentada dentro de cada investigação para preservar o contexto da
            seleção humana e evitar vínculos apenas por semelhança de nome.
          </p>
        </div>
        <Badge tone="info">Dados sintéticos</Badge>
      </section>

      <p className="semantic-boundary-banner semantic-boundary-banner--strong">
        <strong>Não existe catálogo empresarial global nesta interface.</strong>
        Nenhuma entidade é consultada, confirmada ou vinculada em fonte externa por esta rota.
      </p>

      <div className="entity-boundary-grid">
        <Card title="Escopo atual">
          <ul className="scope-list">
            <li>Entidades aparecem somente em modelos de leitura sintéticos de investigação.</li>
            <li>A confirmação demonstrada preserva uma escolha humana explícita.</li>
            <li>Candidatos e fatores de correspondência não constituem Evidence ou Claim.</li>
          </ul>
        </Card>
        <Card title="Onde consultar">
          <p className="card__summary entity-access-copy">
            Abra uma investigação para revisar nome legal, identificadores, jurisdição, aliases e a
            base sintética usada na confirmação.
          </p>
          <Link className="button button--primary" to="/investigacoes">
            Ver investigações
          </Link>
        </Card>
      </div>
    </div>
  );
}
