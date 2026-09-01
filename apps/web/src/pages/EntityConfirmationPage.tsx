import { useEffect, useState } from "react";
import type { SyntheticEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { getInvestigationDetailPath } from "../app/navigation";
import { Badge, Button, Card, Skeleton, StatePanel } from "../components/ui";
import type { EntityCandidate } from "../data/types";
import type {
  EntityCandidateSearchResult,
  InvestigationWorkflow,
} from "../workflow/InvestigationWorkflow";
import { fixtureInvestigationWorkflow } from "../workflow/fixtures/FixtureInvestigationWorkflow";

interface EntityConfirmationPageProps {
  readonly workflow?: InvestigationWorkflow;
}

type CandidateLoadState =
  | { readonly status: "loading" }
  | { readonly status: "error" }
  | { readonly status: "ready"; readonly result: EntityCandidateSearchResult };

const matchStrengthLabels: Readonly<Record<EntityCandidate["matchStrength"], string>> = {
  HIGH: "Mais sinais coincidentes",
  MEDIUM: "Alguns sinais coincidentes",
  LOW: "Poucos sinais coincidentes",
  EXCLUDED: "Candidato não elegível para seleção",
};

function getMatchTone(
  strength: EntityCandidate["matchStrength"],
): "neutral" | "info" | "warning" | "danger" {
  if (strength === "HIGH") return "info";
  if (strength === "EXCLUDED") return "danger";
  if (strength === "LOW") return "warning";
  return "neutral";
}

export function EntityConfirmationPage({
  workflow = fixtureInvestigationWorkflow,
}: EntityConfirmationPageProps) {
  const navigate = useNavigate();
  const [searchParameters] = useSearchParams();
  const identifier = searchParameters.get("identifier")?.trim() ?? "";
  const [loadState, setLoadState] = useState<CandidateLoadState>({ status: "loading" });
  const [retryVersion, setRetryVersion] = useState(0);
  const [selectedCandidateId, setSelectedCandidateId] = useState("");
  const [isConfirming, setIsConfirming] = useState(false);
  const [commandError, setCommandError] = useState(false);

  useEffect(() => {
    if (identifier === "") return;
    let isCurrent = true;
    void workflow.searchEntityCandidates({ identifier }).then(
      (result) => {
        if (isCurrent) setLoadState({ status: "ready", result });
      },
      () => {
        if (isCurrent) setLoadState({ status: "error" });
      },
    );
    return () => {
      isCurrent = false;
    };
  }, [identifier, retryVersion, workflow]);

  async function handleConfirmation(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loadState.status !== "ready" || selectedCandidateId === "") return;
    setCommandError(false);
    setIsConfirming(true);
    try {
      const created = await workflow.createInvestigation({
        candidateId: selectedCandidateId,
        searchReference: loadState.result.searchReference,
      });
      const confirmed = await workflow.confirmEntity({
        candidateId: selectedCandidateId,
        investigationId: created.investigationId,
      });
      await navigate(getInvestigationDetailPath(confirmed.investigationId));
    } catch {
      setCommandError(true);
      setIsConfirming(false);
    }
  }

  const refinePath = `/investigacoes/nova?${new URLSearchParams({ identifier }).toString()}`;

  if (identifier === "") {
    return (
      <StatePanel kind="empty" title="Busca não informada">
        Retorne à etapa anterior e informe um identificador para recuperar os candidatos.
        <div className="state-panel__inline-action">
          <Link className="button button--secondary" to="/investigacoes/nova">
            Voltar à busca
          </Link>
        </div>
      </StatePanel>
    );
  }

  return (
    <div className="page-stack investigation-flow-page">
      <section className="page-intro" aria-labelledby="entity-confirmation-title">
        <div>
          <p className="flow-step">Etapa 2 de 3</p>
          <h2 id="entity-confirmation-title">Confirmar a entidade correta</h2>
          <p>
            Compare identificadores, jurisdição e sinais de correspondência. Sem esta seleção
            humana, nenhuma entidade deve ser vinculada à investigação.
          </p>
        </div>
        <Badge tone="warning">Revisão humana necessária</Badge>
      </section>

      <Card className="search-context-card">
        <p className="card__eyebrow">Identificador pesquisado</p>
        <strong>{identifier}</strong>
        <p>Resultado sintético local; não representa consulta a registro ou fonte externa.</p>
      </Card>

      {loadState.status === "loading" ? (
        <section
          aria-busy="true"
          aria-label="Carregando candidatos de entidade"
          className="candidate-grid"
          role="status"
        >
          <Card>
            <Skeleton height="10rem" />
          </Card>
          <Card>
            <Skeleton height="10rem" />
          </Card>
        </section>
      ) : null}

      {loadState.status === "error" ? (
        <StatePanel
          actionLabel="Tentar novamente"
          kind="error"
          onAction={() => {
            setLoadState({ status: "loading" });
            setRetryVersion((current) => current + 1);
          }}
          title="Não foi possível recuperar os candidatos"
        >
          O adapter de comandos sintético falhou. Nenhuma integração externa foi acionada.
        </StatePanel>
      ) : null}

      {loadState.status === "ready" && loadState.result.candidates.length === 0 ? (
        <StatePanel kind="empty" title="Nenhum candidato encontrado">
          Refine a busca com outro identificador; a investigação ainda não foi criada.
          <div className="state-panel__inline-action">
            <Link className="button button--secondary" to={refinePath}>
              Refinar busca
            </Link>
          </div>
        </StatePanel>
      ) : null}

      {loadState.status === "ready" && loadState.result.candidates.length > 0 ? (
        <form
          className="candidate-selection"
          onSubmit={(event) => {
            void handleConfirmation(event);
          }}
        >
          <fieldset disabled={isConfirming}>
            <legend>
              {loadState.result.candidates.length.toLocaleString("pt-BR")} candidatos encontrados
            </legend>
            <div className="candidate-grid">
              {loadState.result.candidates.map((candidate) => {
                const isSelected = selectedCandidateId === candidate.id;
                const isExcluded = candidate.matchStrength === "EXCLUDED";
                return (
                  <label
                    className={`candidate-card ${isSelected ? "candidate-card--selected" : ""}`.trim()}
                    key={candidate.id}
                  >
                    <input
                      checked={isSelected}
                      disabled={isExcluded}
                      name="entity-candidate"
                      onChange={() => {
                        setSelectedCandidateId(candidate.id);
                      }}
                      type="radio"
                      value={candidate.id}
                    />
                    <span className="candidate-card__content">
                      <span className="candidate-card__heading">
                        <strong>{candidate.legalName}</strong>
                        <Badge tone={getMatchTone(candidate.matchStrength)}>
                          {matchStrengthLabels[candidate.matchStrength]}
                        </Badge>
                      </span>
                      <span className="candidate-card__metadata">
                        <span>
                          <small>Identificador principal</small>
                          <strong>
                            {candidate.primaryIdentifier?.value ?? "Não disponível na fixture"}
                          </strong>
                        </span>
                        <span>
                          <small>Jurisdição</small>
                          <strong>
                            {candidate.jurisdiction.label} ({candidate.jurisdiction.code})
                          </strong>
                        </span>
                      </span>
                      <span className="candidate-card__section">
                        <small>Aliases observados</small>
                        <span>{candidate.aliases.join(", ") || "Nenhum alias informado"}</span>
                      </span>
                      <span className="candidate-card__section">
                        <small>Fatores de correspondência</small>
                        <ul>
                          {candidate.matchingSignals.map((signal) => (
                            <li key={signal}>{signal}</li>
                          ))}
                        </ul>
                      </span>
                      <span className="candidate-card__ambiguity">
                        <strong>Ambiguidade:</strong> {candidate.ambiguityNote}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {commandError ? (
            <p className="command-error" role="alert">
              A confirmação sintética falhou. A investigação não foi alterada; tente novamente.
            </p>
          ) : null}

          <div className="flow-actions flow-actions--sticky">
            <Button disabled={selectedCandidateId === ""} isLoading={isConfirming} type="submit">
              Confirmar entidade
            </Button>
            <Link className="button button--secondary" to={refinePath}>
              Refinar busca
            </Link>
            <Link className="button button--ghost" to="/investigacoes/nova">
              Voltar
            </Link>
          </div>
        </form>
      ) : null}
    </div>
  );
}
