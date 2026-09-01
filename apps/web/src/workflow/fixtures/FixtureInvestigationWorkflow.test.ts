import { describe, expect, it } from "vitest";

import { FixtureInvestigationWorkflow } from "./FixtureInvestigationWorkflow";

describe("FixtureInvestigationWorkflow", () => {
  it("searches deterministic typed candidates without network access", async () => {
    const workflow = new FixtureInvestigationWorkflow();
    const result = await workflow.searchEntityCandidates({ identifier: "BR-FX-000184" });

    expect(result.searchReference).toBe("fixture-search:br-fx-000184");
    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0]?.legalName).toBe("Atlas Meridian Comércio S.A.");
  });

  it("supports an explicit no-candidates fixture scenario", async () => {
    const workflow = new FixtureInvestigationWorkflow({ scenario: "empty" });
    await expect(workflow.searchEntityCandidates({ identifier: "Atlas" })).resolves.toMatchObject({
      candidates: [],
    });
  });

  it("creates and confirms through the mock command boundary", async () => {
    const workflow = new FixtureInvestigationWorkflow();
    const created = await workflow.createInvestigation({
      candidateId: "candidate-atlas-01",
      searchReference: "fixture-search:atlas",
    });
    const confirmed = await workflow.confirmEntity({
      candidateId: "candidate-atlas-01",
      investigationId: created.investigationId,
    });

    expect(created.lifecycleStatus).toBe("WAITING_FOR_ENTITY_CONFIRMATION");
    expect(confirmed).toEqual({
      entityId: "entity-atlas-meridian",
      investigationId: "inv-atlas-meridian",
    });
  });

  it("fails explicitly in the error scenario", async () => {
    const workflow = new FixtureInvestigationWorkflow({ scenario: "error" });
    await expect(workflow.searchEntityCandidates({ identifier: "Atlas" })).rejects.toThrow(
      "fluxo sintético",
    );
  });
});
