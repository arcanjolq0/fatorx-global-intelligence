import { describe, expect, it } from "vitest";

import {
  FixtureDataSourceError,
  FixtureIntelligenceDataSource,
} from "./FixtureIntelligenceDataSource";

describe("FixtureIntelligenceDataSource", () => {
  it("provides coherent typed read models without sharing mutable fixture references", async () => {
    const dataSource = new FixtureIntelligenceDataSource();

    const [dashboard, investigations, evidence, claims, reviews, activity] = await Promise.all([
      dataSource.getDashboardSummary(),
      dataSource.listInvestigations(),
      dataSource.listEvidence(),
      dataSource.listClaims(),
      dataSource.listFactualReviews(),
      dataSource.getRecentActivity(),
    ]);

    expect(investigations).toHaveLength(5);
    expect(dashboard).toMatchObject({
      totalInvestigations: investigations.length,
      evidenceItems: evidence.length,
      claims: claims.length,
    });
    expect(reviews).toHaveLength(claims.length);
    expect(activity.length).toBeGreaterThan(0);

    const secondRead = await dataSource.listInvestigations();
    expect(secondRead).toEqual(investigations);
    expect(secondRead).not.toBe(investigations);
  });

  it("keeps contextual eligibility, global admissibility and factual review separate", async () => {
    const dataSource = new FixtureIntelligenceDataSource();
    const claims = await dataSource.listClaims();
    const reviewStates = new Set(claims.map((claim) => claim.factualReview.effectiveStatus));
    const conflictedClaim = claims.find((claim) => claim.assessment === "CONFLICTED");

    expect(reviewStates).toEqual(
      new Set(["ACCEPTED", "PENDING", "REJECTED", "NEEDS_CORRECTION", "INVALIDATED"]),
    );
    expect(conflictedClaim?.evidenceUses).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          role: "SUPPORTS",
          eligibility: {
            purpose: "INTERNAL_CLAIM_VERIFICATION",
            status: "ELIGIBLE",
          },
          admissibility: {
            purpose: "INTERNAL_FACTUAL_EVIDENCE_USE",
            status: "ADMISSIBLE",
          },
        }),
        expect.objectContaining({ role: "CONTRADICTS" }),
      ]),
    );
    expect(conflictedClaim?.factualReview).toMatchObject({
      purpose: "INTERNAL_FACTUAL_CLAIM_USE",
      decisionOutcome: "NEEDS_CORRECTION",
      effectiveStatus: "NEEDS_CORRECTION",
    });
  });

  it("supports scoped reads and an absent detail without inventing a remote lookup", async () => {
    const dataSource = new FixtureIntelligenceDataSource();

    await expect(dataSource.listEvidence("inv-rheinbruck-machines")).resolves.toHaveLength(1);
    await expect(dataSource.listClaims("inv-rheinbruck-machines")).resolves.toEqual([]);
    await expect(dataSource.getInvestigationDetail("inv-atlas-meridian")).resolves.toMatchObject({
      id: "inv-atlas-meridian",
      entity: { legalName: "Atlas Meridian Comércio S.A." },
    });
    await expect(dataSource.getInvestigationDetail("inv-inexistente")).resolves.toBeNull();
  });

  it("exposes deterministic empty and error scenarios", async () => {
    const emptyDataSource = new FixtureIntelligenceDataSource({ scenario: "empty" });
    const errorDataSource = new FixtureIntelligenceDataSource({ scenario: "error" });

    await expect(emptyDataSource.listInvestigations()).resolves.toEqual([]);
    await expect(emptyDataSource.getDashboardSummary()).resolves.toMatchObject({
      totalInvestigations: 0,
      evidenceItems: 0,
      claims: 0,
    });
    await expect(errorDataSource.listInvestigations()).rejects.toBeInstanceOf(
      FixtureDataSourceError,
    );
  });

  it("rejects invalid synthetic latency configuration", () => {
    expect(() => new FixtureIntelligenceDataSource({ delayMs: -1 })).toThrow(RangeError);
    expect(() => new FixtureIntelligenceDataSource({ delayMs: 1.5 })).toThrow(RangeError);
  });
});
