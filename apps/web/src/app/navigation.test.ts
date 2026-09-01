import { describe, expect, it } from "vitest";

import { appRoutes, getRouteBreadcrumbs, getRouteByPathname } from "./navigation";

const expectedPaths = [
  "/",
  "/investigacoes",
  "/investigacoes/nova",
  "/entidades",
  "/evidencias",
  "/claims",
  "/revisoes",
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
});
