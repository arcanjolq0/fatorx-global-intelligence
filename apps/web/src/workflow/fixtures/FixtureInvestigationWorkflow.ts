import { entitySearchCandidates } from "../../data/fixtures/intelligenceFixtures";
import type { EntityCandidate } from "../../data/types";
import type {
  ConfirmedEntityResult,
  ConfirmEntityCommand,
  CreatedInvestigation,
  CreateInvestigationCommand,
  EntityCandidateSearchResult,
  InvestigationWorkflow,
  SearchEntityCandidatesCommand,
} from "../InvestigationWorkflow";

export type FixtureWorkflowScenario = "candidates" | "empty" | "error";

export interface FixtureInvestigationWorkflowOptions {
  readonly delayMs?: number;
  readonly scenario?: FixtureWorkflowScenario;
}

export class FixtureInvestigationWorkflowError extends Error {
  constructor() {
    super("Não foi possível concluir a operação no fluxo sintético.");
    this.name = "FixtureInvestigationWorkflowError";
  }
}

const candidateDestinations: Readonly<
  Record<string, { readonly entityId: string; readonly investigationId: string }>
> = {
  "candidate-atlas-01": {
    entityId: "entity-atlas-meridian",
    investigationId: "inv-atlas-meridian",
  },
  "candidate-solandia-01": {
    entityId: "entity-solandia-exports",
    investigationId: "inv-solandia-exports",
  },
};

function normalizeIdentifier(identifier: string): string {
  return identifier
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("pt-BR")
    .trim();
}

function buildSearchReference(identifier: string): string {
  return `fixture-search:${encodeURIComponent(identifier)}`;
}

function candidateMatches(candidate: EntityCandidate, identifier: string): boolean {
  const searchable = [
    candidate.legalName,
    ...candidate.aliases,
    candidate.primaryIdentifier?.value ?? "",
    candidate.jurisdiction.code,
    candidate.jurisdiction.label,
  ]
    .map(normalizeIdentifier)
    .join(" ");
  return searchable.includes(identifier);
}

export class FixtureInvestigationWorkflow implements InvestigationWorkflow {
  readonly #delayMs: number;
  readonly #scenario: FixtureWorkflowScenario;

  constructor({ delayMs = 0, scenario = "candidates" }: FixtureInvestigationWorkflowOptions = {}) {
    if (!Number.isSafeInteger(delayMs) || delayMs < 0) {
      throw new RangeError("delayMs deve ser um inteiro seguro não negativo.");
    }
    this.#delayMs = delayMs;
    this.#scenario = scenario;
  }

  async searchEntityCandidates(
    command: SearchEntityCandidatesCommand,
  ): Promise<EntityCandidateSearchResult> {
    await this.#waitAndMaybeFail();
    const normalizedIdentifier = normalizeIdentifier(command.identifier);
    const matchingCandidates = entitySearchCandidates.filter((candidate) =>
      candidateMatches(candidate, normalizedIdentifier),
    );

    return structuredClone({
      candidates:
        this.#scenario === "empty"
          ? []
          : matchingCandidates.length > 0
            ? matchingCandidates
            : entitySearchCandidates,
      normalizedIdentifier,
      searchReference: buildSearchReference(normalizedIdentifier),
    });
  }

  async createInvestigation(command: CreateInvestigationCommand): Promise<CreatedInvestigation> {
    await this.#waitAndMaybeFail();
    const destination = candidateDestinations[command.candidateId];
    if (destination === undefined || !command.searchReference.startsWith("fixture-search:")) {
      throw new FixtureInvestigationWorkflowError();
    }
    return {
      investigationId: destination.investigationId,
      lifecycleStatus: "WAITING_FOR_ENTITY_CONFIRMATION",
    };
  }

  async confirmEntity(command: ConfirmEntityCommand): Promise<ConfirmedEntityResult> {
    await this.#waitAndMaybeFail();
    const destination = candidateDestinations[command.candidateId];
    if (destination?.investigationId !== command.investigationId) {
      throw new FixtureInvestigationWorkflowError();
    }
    return structuredClone(destination);
  }

  async #waitAndMaybeFail(): Promise<void> {
    if (this.#delayMs > 0) {
      await new Promise<void>((resolve) => {
        globalThis.setTimeout(resolve, this.#delayMs);
      });
    }
    if (this.#scenario === "error") {
      throw new FixtureInvestigationWorkflowError();
    }
  }
}

export const fixtureInvestigationWorkflow = new FixtureInvestigationWorkflow({ delayMs: 180 });
