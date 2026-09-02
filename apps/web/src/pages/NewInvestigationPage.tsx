import { useRef, useState } from "react";
import type { SyntheticEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { getEntityConfirmationPath } from "../app/navigation";
import { Badge, Button, Card, Input, Skeleton, StatePanel } from "../components/ui";
import type { InvestigationWorkflow } from "../workflow/InvestigationWorkflow";
import { fixtureInvestigationWorkflow } from "../workflow/fixtures/FixtureInvestigationWorkflow";

interface NewInvestigationPageProps {
  readonly workflow?: InvestigationWorkflow;
}

type SearchStatus = "default" | "loading" | "empty" | "error";

function validateIdentifier(value: string): string | undefined {
  const trimmedValue = value.trim();
  if (trimmedValue === "") return "Informe ao menos um identificador da empresa.";
  if (trimmedValue.length < 3) return "Use pelo menos 3 caracteres para refinar a busca.";
  if (trimmedValue.length > 160) return "Use no máximo 160 caracteres.";
  return undefined;
}

export function NewInvestigationPage({
  workflow = fixtureInvestigationWorkflow,
}: NewInvestigationPageProps) {
  const navigate = useNavigate();
  const [searchParameters] = useSearchParams();
  const [identifier, setIdentifier] = useState(
    () => searchParameters.get("identifier")?.slice(0, 160) ?? "",
  );
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<SearchStatus>("default");
  const inputReference = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validateIdentifier(identifier);
    if (validationError !== undefined) {
      setError(validationError);
      setStatus("default");
      inputReference.current?.focus();
      return;
    }

    setError(undefined);
    setStatus("loading");
    try {
      const result = await workflow.searchEntityCandidates({ identifier: identifier.trim() });
      if (result.candidates.length === 0) {
        setStatus("empty");
        return;
      }
      await navigate(getEntityConfirmationPath(identifier.trim()));
    } catch {
      setStatus("error");
    }
  }

  function refineSearch() {
    setStatus("default");
    inputReference.current?.focus();
  }

  return (
    <div className="page-stack investigation-flow-page">
      <section className="page-intro" aria-labelledby="new-investigation-title">
        <div>
          <p className="flow-step">Etapa 1 de 3</p>
          <h2 id="new-investigation-title">Localizar a empresa investigada</h2>
          <p>
            Comece por um dado que ajude a diferenciar a entidade. A seleção final será sempre
            confirmada na próxima etapa.
          </p>
        </div>
        <Badge tone="info">Demonstração com fixtures</Badge>
      </section>

      <Card className="investigation-search-card">
        <form
          className="investigation-search-form"
          noValidate
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
        >
          <Input
            autoComplete="off"
            disabled={status === "loading"}
            error={error}
            helperText="Exemplo sintético: Atlas Meridian, BR-FX-000184 ou atlas-meridian.example."
            label="Empresa, documento, domínio, telefone ou outro identificador"
            maxLength={160}
            onBlur={() => {
              if (identifier.trim() !== "") setError(validateIdentifier(identifier));
            }}
            onChange={(event) => {
              setIdentifier(event.target.value);
              if (error !== undefined) setError(undefined);
            }}
            placeholder="Digite um identificador conhecido"
            ref={inputReference}
            required
            type="search"
            value={identifier}
          />
          <div className="flow-actions">
            <Button isLoading={status === "loading"} type="submit">
              Buscar candidatos
            </Button>
            <Link className="button button--ghost" to="/investigacoes">
              Cancelar
            </Link>
          </div>
        </form>
        <p className="mock-boundary-note">
          Esta busca usa somente dados sintéticos locais. Nenhuma consulta externa ou criação no
          backend será realizada.
        </p>
      </Card>

      {status === "loading" ? (
        <section
          aria-busy="true"
          aria-label="Buscando candidatos sintéticos"
          className="flow-loading-card"
          role="status"
        >
          <Skeleton height="1rem" width="32%" />
          <Skeleton height="5.5rem" width="100%" />
          <Skeleton height="5.5rem" width="100%" />
        </section>
      ) : null}

      {status === "empty" ? (
        <StatePanel
          actionLabel="Refinar busca"
          kind="empty"
          onAction={refineSearch}
          title="Nenhum candidato encontrado"
        >
          Revise o identificador ou tente outro dado da empresa. A investigação não foi criada.
        </StatePanel>
      ) : null}

      {status === "error" ? (
        <StatePanel
          actionLabel="Tentar novamente"
          kind="error"
          onAction={refineSearch}
          title="Não foi possível buscar candidatos"
        >
          O adaptador sintético não respondeu. Revise o dado e tente novamente; nenhuma chamada de
          rede foi feita.
        </StatePanel>
      ) : null}
    </div>
  );
}
