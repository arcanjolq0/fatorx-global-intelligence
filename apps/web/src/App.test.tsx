import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { App } from "./App";
import { router } from "./app/router";

describe("App", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(async () => {
    await router.navigate("/");
  });

  it("renders the accessible application foundation without business data", () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Visão Geral" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Módulos da aplicação" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Investigações" })).toHaveAttribute(
      "href",
      "/investigacoes",
    );
    expect(screen.getByText("Módulo ainda não implementado")).toBeVisible();

    const search = screen.getByRole("searchbox", { name: "Busca global" });
    expect(search).toHaveAttribute("readonly");
    expect(search).toHaveAttribute("aria-disabled", "true");

    const skipLink = screen.getByRole("link", { name: "Ir para o conteúdo principal" });
    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(document.querySelector("main")).toHaveAttribute("id", "main-content");
  });

  it("uses the shared route configuration for nested route context", async () => {
    await router.navigate("/investigacoes/nova");
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Nova investigação" })).toBeVisible();
    const breadcrumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(breadcrumb).getByRole("link", { name: "Investigações" })).toHaveAttribute(
      "href",
      "/investigacoes",
    );
    expect(within(breadcrumb).getByText("Nova investigação")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.getByRole("heading", { level: 2, name: "Localizar a empresa investigada" }),
    ).toBeVisible();
  });

  it("renders an explicit not-found route", async () => {
    await router.navigate("/rota-inexistente");
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Página não encontrada" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Voltar à Visão Geral" })).toHaveAttribute("href", "/");
  });
});
