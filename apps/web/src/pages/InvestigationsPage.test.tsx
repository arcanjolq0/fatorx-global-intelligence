import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import {
  FixtureIntelligenceDataSource,
  type FixtureScenario,
} from "../data/fixtures/FixtureIntelligenceDataSource";
import type { InvestigationSummary } from "../data/types";
import { InvestigationsPage } from "./InvestigationsPage";

class PendingFixtureDataSource extends FixtureIntelligenceDataSource {
  override listInvestigations(): Promise<readonly InvestigationSummary[]> {
    return new Promise(() => undefined);
  }
}

function renderPage(scenario: FixtureScenario = "populated") {
  const dataSource = new FixtureIntelligenceDataSource({ scenario });
  return render(
    <MemoryRouter initialEntries={["/investigacoes"]}>
      <Routes>
        <Route path="/investigacoes" element={<InvestigationsPage dataSource={dataSource} />} />
        <Route
          path="/investigacoes/:investigationId"
          element={<h2>Detalhe estrutural da investigação</h2>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
});

describe("InvestigationsPage", () => {
  it("renders populated synthetic investigations with requested presentation fields", async () => {
    renderPage();

    const table = await screen.findByRole("table", { name: "Investigações sintéticas" });
    expect(within(table).getAllByRole("row")).toHaveLength(6);
    const atlasLink = screen.getByRole("link", { name: "Atlas Meridian Comércio S.A." });
    expect(atlasLink).toHaveAttribute("href", "/investigacoes/inv-atlas-meridian");
    const atlasRow = atlasLink.closest("tr");
    if (atlasRow === null) {
      throw new Error("A investigação deve ser renderizada em uma linha semântica.");
    }
    expect(within(atlasRow).getByText("BR-FX-000184")).toBeVisible();
    expect(within(atlasRow).getByText("Aguardando revisão")).toBeVisible();
    expect(within(atlasRow).getByText("4")).toBeVisible();
    expect(within(atlasRow).getByText("1 claim")).toBeVisible();
    expect(within(atlasRow).getByText("1 revisão")).toBeVisible();
  });

  it("renders a useful empty scenario", async () => {
    renderPage("empty");

    expect(await screen.findByText("Nenhuma investigação disponível")).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("0 de 0 investigações")).toBeVisible();
  });

  it("announces fixture errors without performing a network request", async () => {
    renderPage("error");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Não foi possível carregar as investigações");
    expect(alert).toHaveTextContent("Nenhuma chamada de rede foi realizada");
    expect(screen.getByRole("button", { name: "Tentar novamente" })).toBeVisible();
  });

  it("shows an accessible loading state", () => {
    render(
      <MemoryRouter>
        <InvestigationsPage dataSource={new PendingFixtureDataSource()} />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText("Carregando lista de investigações")).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "Buscar investigações" })).toBeDisabled();
  });

  it("filters locally by normalized search and lifecycle state", async () => {
    renderPage();
    await screen.findByRole("table", { name: "Investigações sintéticas" });

    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar investigações" }), {
      target: { value: "comercio" },
    });
    expect(screen.getByRole("link", { name: "Atlas Meridian Comércio S.A." })).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Northstar Components Ltd." }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar investigações" }), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Filtrar por estado" }), {
      target: { value: "COLLECTING" },
    });
    expect(screen.getByRole("link", { name: "Rheinbruck Maschinen GmbH" })).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Atlas Meridian Comércio S.A." }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("1 de 5 investigações")).toBeVisible();
  });

  it("navigates from an investigation row to the detail placeholder", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("link", { name: "Atlas Meridian Comércio S.A." }));

    expect(
      await screen.findByRole("heading", { name: "Detalhe estrutural da investigação" }),
    ).toBeVisible();
  });
});
