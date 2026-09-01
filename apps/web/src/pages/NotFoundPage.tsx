import { Link } from "react-router";

import { Card } from "../components/ui";

export function NotFoundPage() {
  return (
    <Card className="not-found">
      <p className="eyebrow">404</p>
      <h2 id="page-title">Endereço indisponível</h2>
      <p>Este endereço não faz parte da foundation atual.</p>
      <Link className="button button--primary" to="/">
        Voltar à Visão Geral
      </Link>
    </Card>
  );
}
