import { Link } from "react-router";

import { Card } from "../components/ui";

export function NotFoundPage() {
  return (
    <Card className="not-found">
      <p className="eyebrow">404</p>
      <h2 id="page-title">Página não encontrada</h2>
      <p>O endereço pode ter mudado ou não pertence às rotas disponíveis nesta interface.</p>
      <Link className="button button--primary" to="/">
        Voltar à Visão Geral
      </Link>
    </Card>
  );
}
