import { describe, expect, it } from "vitest";

import {
  FixtureDataSourceError,
  FixtureIntelligenceDataSource,
} from "./FixtureIntelligenceDataSource";

describe("FixtureIntelligenceDataSource", () => {
  it("provides coherent typed read models without sharing mutable fixture references", async () => {
    const dataSource = new FixtureIntelligenceDataSource();

    const [
      dashboard,
      investigations,
      evidence,
      claims,
      reviews,
      activity,
      sources,
      audit,
      reports,
    ] = await Promise.all([
      dataSource.getDashboardSummary(),
      dataSource.listInvestigations(),
      dataSource.listEvidence(),
      dataSource.listClaims(),
      dataSource.listFactualReviews(),
      dataSource.getRecentActivity(),
      dataSource.listControlledSources(),
      dataSource.listAuditEvents(),
      dataSource.listReportPreviews(),
    ]);

    expect(investigations).toHaveLength(5);
    expect(dashboard).toMatchObject({
      totalInvestigations: investigations.length,
      evidenceItems: evidence.length,
      claims: claims.length,
    });
    expect(reviews).toHaveLength(claims.length);
    expect(activity.length).toBeGreaterThan(0);
    expect(sources).toHaveLength(4);
    expect(new Set(sources.map((source) => source.status))).toEqual(
      new Set(["CONTROLLED_TEST_FIXTURE", "TEST_SUSPENDED"]),
    );
    expect(audit).toHaveLength(6);
    expect(reports).toHaveLength(investigations.length);
    expect(reports.find((report) => report.availability === "PREVIEW_AVAILABLE")).toMatchObject({
      investigationId: "inv-atlas-meridian",
      traceability: [
        {
          claimId: "claim-atlas-legal-name",
          claimVersion: 1,
          factualReviewId: "review-01",
        },
      ],
    });

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
        expect.objectContaining({ role: "QUALIFIES" }),
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
    await expect(
      dataSource.getClaimDetail("claim-northstar-registration-status"),
    ).resolves.toMatchObject({ version: 2, assessment: "CONFLICTED" });
    await expect(dataSource.getFactualReviewDetail("review-02")).resolves.toMatchObject({
      claimId: "claim-atlas-prior-identifier",
      claimVersion: 1,
      effectiveStatus: "INVALIDATED",
    });
    await expect(dataSource.getClaimDetail("claim-inexistente")).resolves.toBeNull();
    await expect(dataSource.getFactualReviewDetail("review-inexistente")).resolves.toBeNull();
  });

  it("preserves persisted Evidence PENDING independently from every effective F5.3 state", async () => {
    const evidence = await new FixtureIntelligenceDataSource().listEvidence();
    expect(new Set(evidence.map((item) => item.persistedAdmissibilityStatus))).toEqual(
      new Set(["PENDING"]),
    );
    expect(new Set(evidence.map((item) => item.admissibility.status))).toEqual(
      new Set(["PENDING", "ADMISSIBLE", "RESTRICTED", "REJECTED", "EXPIRED", "REVOKED"]),
    );
  });

  it("exposes deterministic empty and error scenarios", async () => {
    const emptyDataSource = new FixtureIntelligenceDataSource({ scenario: "empty" });
    const errorDataSource = new FixtureIntelligenceDataSource({ scenario: "error" });

    await expect(emptyDataSource.listInvestigations()).resolves.toEqual([]);
    await expect(emptyDataSource.getDashboardSummary()).resolves.toMatchObject({
      totalInvestigations: 0,
      evidenceItems: 0,
      claims: 0,
      pendingReviews: 0,
    });
    await expect(emptyDataSource.listControlledSources()).resolves.toEqual([]);
    await expect(emptyDataSource.listAuditEvents()).resolves.toEqual([]);
    await expect(emptyDataSource.listReportPreviews()).resolves.toEqual([]);
    await expect(errorDataSource.listInvestigations()).rejects.toBeInstanceOf(
      FixtureDataSourceError,
    );
  });

  it("rejects invalid synthetic latency configuration", () => {
    expect(() => new FixtureIntelligenceDataSource({ delayMs: -1 })).toThrow(RangeError);
    expect(() => new FixtureIntelligenceDataSource({ delayMs: 1.5 })).toThrow(RangeError);
  });
});
