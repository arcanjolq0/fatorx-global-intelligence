import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { FixtureInvestigationWorkflow } from "../workflow/fixtures/FixtureInvestigationWorkflow";
import { EntityConfirmationPage } from "./EntityConfirmationPage";

function renderPage(
  workflow = new FixtureInvestigationWorkflow(),
  entry = "/investigacoes/nova/confirmacao?identifier=Atlas",
) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route
          path="/investigacoes/nova/confirmacao"
          element={<EntityConfirmationPage workflow={workflow} />}
        />
        <Route path="/investigacoes/:investigationId" element={<h2>Detalhe alcançado</h2>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("EntityConfirmationPage", () => {
  it("shows cautious candidate factors and provides recoverable back paths", async () => {
    renderPage();
    const radio = await screen.findByRole("radio", { name: /Atlas Meridian Comércio S.A./i });
    expect(radio).toBeVisible();
    expect(screen.getByText("Mais sinais coincidentes")).toBeVisible();
    expect(screen.getByText(/Ambiguidade:/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Refinar busca" })).toHaveAttribute(
      "href",
      "/investigacoes/nova?identifier=Atlas",
    );
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("supports native keyboard selection semantics and navigates after confirmation", async () => {
    renderPage();
    const radio = await screen.findByRole("radio", { name: /Atlas Meridian Comércio S.A./i });
    radio.focus();
    expect(radio).toHaveFocus();
    fireEvent.click(radio);
    expect(radio).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar entidade" }));
    expect(await screen.findByRole("heading", { name: "Detalhe alcançado" })).toBeVisible();
  });

  it("covers missing-query, empty, loading and error states", async () => {
    const { unmount } = renderPage(
      new FixtureInvestigationWorkflow(),
      "/investigacoes/nova/confirmacao",
    );
    expect(screen.getByText("Busca não informada")).toBeVisible();
    unmount();

    const emptyRender = renderPage(new FixtureInvestigationWorkflow({ scenario: "empty" }));
    expect(await screen.findByText("Nenhum candidato encontrado")).toBeVisible();
    emptyRender.unmount();

    const loadingRender = renderPage(new FixtureInvestigationWorkflow({ delayMs: 10_000 }));
    expect(screen.getByLabelText("Carregando candidatos de entidade")).toBeVisible();
    loadingRender.unmount();

    renderPage(new FixtureInvestigationWorkflow({ scenario: "error" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível recuperar os candidatos",
    );
  });
});
