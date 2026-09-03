import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { router } from "./app/router";

describe("App", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(async () => {
    await router.navigate("/");
  });

  it("renders the accessible application shell with the fixture dashboard", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Visão Geral" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Módulos da aplicação" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Investigações" })).toHaveAttribute(
      "href",
      "/investigacoes",
    );
    expect(
      await screen.findByRole("heading", { level: 2, name: "Visão consolidada do workspace" }),
    ).toBeVisible();

    const search = screen.getByRole("searchbox", { name: "Busca global" });
    expect(search).toBeDisabled();

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

  it("traps focus in the mobile navigation and restores it when dismissed", () => {
    render(<App />);
    const menuButton = screen.getByRole("button", { name: "Abrir menu" });
    menuButton.focus();
    fireEvent.click(menuButton);

    expect(screen.getByRole("dialog", { name: "Navegação principal" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Visão Geral" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(menuButton).toHaveFocus();
  });

  it.each([390, 1440])(
    "keeps the route focus and shell controls available at %ipx",
    async (viewportWidth) => {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: viewportWidth });
      const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
      render(<App />);
      scrollTo.mockClear();

      await router.navigate("/investigacoes");
      await screen.findByRole("heading", { level: 1, name: "Investigações" });

      expect(document.querySelector("main")).toHaveFocus();
      expect(scrollTo).toHaveBeenCalledWith({ behavior: "auto", left: 0, top: 0 });
      expect(screen.getByRole("banner", { name: "Barra superior" })).toBeVisible();
      if (viewportWidth === 390) {
        expect(screen.getByRole("button", { name: "Abrir menu" })).toBeVisible();
      }
    },
  );

  it("preserves browser-restored scroll on back navigation while returning focus to main", async () => {
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
    render(<App />);

    await router.navigate("/investigacoes");
    await screen.findByRole("heading", { level: 1, name: "Investigações" });
    scrollTo.mockClear();

    await router.navigate(-1);
    await screen.findByRole("heading", { level: 1, name: "Visão Geral" });

    expect(document.querySelector("main")).toHaveFocus();
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it("renders the honest read-only settings route", async () => {
    await router.navigate("/configuracoes");
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Configurações" })).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 2, name: "Preferências e limites do workspace" }),
    ).toBeVisible();
    expect(screen.getByText("Nenhuma alteração é salva.")).toBeVisible();
  });

  it("renders an explicit not-found route", async () => {
    await router.navigate("/rota-inexistente");
    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "Página não encontrada" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Voltar à Visão Geral" })).toHaveAttribute("href", "/");
  });
});
