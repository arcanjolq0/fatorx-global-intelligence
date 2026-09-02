import { describe, expect, it } from "vitest";

import {
  appRoutes,
  getEntityConfirmationPath,
  getClaimDetailPath,
  getInvestigationDetailPath,
  getReviewDetailPath,
  getRouteBreadcrumbs,
  getRouteByPathname,
} from "./navigation";

const expectedPaths = [
  "/",
  "/investigacoes",
  "/investigacoes/nova",
  "/investigacoes/nova/confirmacao",
  "/investigacoes/:investigationId",
  "/entidades",
  "/evidencias",
  "/claims",
  "/claims/:claimId",
  "/revisoes",
  "/revisoes/:reviewId",
  "/fontes",
  "/relatorios",
  "/auditoria",
  "/configuracoes",
];

describe("navigation configuration", () => {
  it("defines every foundation route once", () => {
    const paths = appRoutes.map((route) => route.path);

    expect(paths).toEqual(expectedPaths);
    expect(new Set(paths).size).toBe(paths.length);
    expect(new Set(appRoutes.map((route) => route.id)).size).toBe(appRoutes.length);
  });

  it("resolves trailing slashes and nested breadcrumbs", () => {
    const route = getRouteByPathname("/investigacoes/nova/");

    expect(route?.id).toBe("new-investigation");
    expect(route === undefined ? [] : getRouteBreadcrumbs(route).map((item) => item.id)).toEqual([
      "investigations",
      "new-investigation",
    ]);
  });

  it("resolves a typed investigation detail path without shadowing the new route", () => {
    expect(getInvestigationDetailPath("inv-atlas-meridian")).toBe(
      "/investigacoes/inv-atlas-meridian",
    );
    expect(getRouteByPathname("/investigacoes/inv-atlas-meridian")?.id).toBe(
      "investigation-detail",
    );
    expect(getRouteByPathname("/investigacoes/nova")?.id).toBe("new-investigation");
    expect(getRouteByPathname("/investigacoes/nova/confirmacao")?.id).toBe("entity-confirmation");
    expect(getEntityConfirmationPath("Atlas & Filhos")).toBe(
      "/investigacoes/nova/confirmacao?identifier=Atlas+%26+Filhos",
    );
  });

  it("builds all breadcrumb levels for entity confirmation", () => {
    const route = getRouteByPathname("/investigacoes/nova/confirmacao");
    expect(route === undefined ? [] : getRouteBreadcrumbs(route).map((item) => item.id)).toEqual([
      "investigations",
      "new-investigation",
      "entity-confirmation",
    ]);
  });

  it("resolves Claim and factual review details from the shared route registry", () => {
    expect(getClaimDetailPath("claim/01")).toBe("/claims/claim%2F01");
    expect(getReviewDetailPath("review 01")).toBe("/revisoes/review%2001");
    expect(getRouteByPathname("/claims/claim-01")?.id).toBe("claim-detail");
    expect(getRouteByPathname("/revisoes/review-01")?.id).toBe("review-detail");
  });
});
