import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import {
  FixtureIntelligenceDataSource,
  type FixtureScenario,
} from "../data/fixtures/FixtureIntelligenceDataSource";
import { AuditPage } from "./AuditPage";

function renderPage(scenario: FixtureScenario = "populated") {
  return render(
    <MemoryRouter>
      <AuditPage dataSource={new FixtureIntelligenceDataSource({ scenario })} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("AuditPage", () => {
  it("renders a safe read-only audit projection without sensitive bodies", async () => {
    renderPage();

    const table = await screen.findByRole("table", { name: "Eventos de auditoria sintéticos" });
    expect(within(table).getAllByRole("row")).toHaveLength(7);
    expect(screen.getByText("Demonstração local · somente leitura")).toBeVisible();
    expect(screen.getByText(/não expõe conteúdo documental/i)).toBeVisible();
    expect(screen.queryByText(/token-|cookie=|secret=/i)).not.toBeInTheDocument();
  });

  it("filters events locally by category, action, investigation and search", async () => {
    renderPage();
    await screen.findByRole("table", { name: "Eventos de auditoria sintéticos" });

    fireEvent.change(screen.getByRole("combobox", { name: "Categoria" }), {
      target: { value: "FACTUAL_REVIEW" },
    });
    expect(screen.getByText("2 de 6 eventos")).toBeVisible();

    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar eventos" }), {
      target: { value: "correção" },
    });
    expect(screen.getByText("1 de 6 eventos")).toBeVisible();
    expect(
      within(screen.getByRole("table", { name: "Eventos de auditoria sintéticos" })).getByText(
        "Revisão factual devolvida para correção",
      ),
    ).toBeVisible();

    fireEvent.change(screen.getByRole("combobox", { name: "Ação" }), {
      target: { value: "Decisão factual invalidada" },
    });
    expect(screen.getByText("Nenhum evento corresponde aos filtros")).toBeVisible();
  });

  it("renders the empty audit state", async () => {
    renderPage("empty");

    expect(await screen.findByText("Nenhum evento corresponde aos filtros")).toBeVisible();
  });
});
