import type { IntelligenceDataSource } from "../IntelligenceDataSource";
import type {
  ActivityItem,
  ClaimReviewSummary,
  ClaimSummary,
  DashboardSummary,
  EvidenceSummary,
  InvestigationDetail,
  InvestigationSummary,
} from "../types";
import { emptyFixtureData, populatedFixtureData } from "./intelligenceFixtures";
import type { FixtureDataSet } from "./intelligenceFixtures";

export type FixtureScenario = "populated" | "empty" | "error";

export interface FixtureDataSourceOptions {
  readonly delayMs?: number;
  readonly scenario?: FixtureScenario;
}

export class FixtureDataSourceError extends Error {
  constructor() {
    super("Não foi possível carregar o cenário sintético solicitado.");
    this.name = "FixtureDataSourceError";
  }
}

export class FixtureIntelligenceDataSource implements IntelligenceDataSource {
  readonly #data: FixtureDataSet;
  readonly #delayMs: number;
  readonly #scenario: FixtureScenario;

  constructor({ delayMs = 0, scenario = "populated" }: FixtureDataSourceOptions = {}) {
    if (!Number.isSafeInteger(delayMs) || delayMs < 0) {
      throw new RangeError("delayMs deve ser um inteiro seguro não negativo.");
    }

    this.#delayMs = delayMs;
    this.#scenario = scenario;
    this.#data = scenario === "empty" ? emptyFixtureData : populatedFixtureData;
  }

  getDashboardSummary(): Promise<DashboardSummary> {
    return this.#read(this.#data.dashboard);
  }

  listInvestigations(): Promise<readonly InvestigationSummary[]> {
    return this.#read(this.#data.investigations);
  }

  getInvestigationDetail(investigationId: string): Promise<InvestigationDetail | null> {
    const investigation =
      this.#data.investigationDetails.find((item) => item.id === investigationId) ?? null;
    return this.#read(investigation);
  }

  listEvidence(investigationId?: string): Promise<readonly EvidenceSummary[]> {
    return this.#read(this.#filterByInvestigation(this.#data.evidence, investigationId));
  }

  listClaims(investigationId?: string): Promise<readonly ClaimSummary[]> {
    return this.#read(this.#filterByInvestigation(this.#data.claims, investigationId));
  }

  listFactualReviews(investigationId?: string): Promise<readonly ClaimReviewSummary[]> {
    return this.#read(this.#filterByInvestigation(this.#data.factualReviews, investigationId));
  }

  getRecentActivity(): Promise<readonly ActivityItem[]> {
    return this.#read(this.#data.recentActivity);
  }

  #filterByInvestigation<Row extends { readonly investigationId: string }>(
    rows: readonly Row[],
    investigationId: string | undefined,
  ): readonly Row[] {
    return investigationId === undefined
      ? rows
      : rows.filter((row) => row.investigationId === investigationId);
  }

  async #read<Value>(value: Value): Promise<Value> {
    if (this.#delayMs > 0) {
      await new Promise<void>((resolve) => {
        globalThis.setTimeout(resolve, this.#delayMs);
      });
    }

    if (this.#scenario === "error") {
      throw new FixtureDataSourceError();
    }

    return structuredClone(value);
  }
}

export const fixtureIntelligenceDataSource = new FixtureIntelligenceDataSource({ delayMs: 180 });
