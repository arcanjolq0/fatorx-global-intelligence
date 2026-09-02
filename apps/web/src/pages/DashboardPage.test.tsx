import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import {
  FixtureIntelligenceDataSource,
  type FixtureScenario,
} from "../data/fixtures/FixtureIntelligenceDataSource";
import { DashboardPage } from "./DashboardPage";

function renderPage(scenario: FixtureScenario = "populated") {
  return render(
    <MemoryRouter>
      <DashboardPage dataSource={new FixtureIntelligenceDataSource({ scenario })} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("DashboardPage", () => {
  it("renders fixture-derived KPIs and the requested operational blocks", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Visão consolidada do workspace" }),
    ).toBeVisible();
    const indicators = screen.getByRole("region", { name: "Indicadores do workspace" });
    expect(within(indicators).getByText("Investigações")).toBeVisible();
    expect(within(indicators).getByText("Evidence")).toBeVisible();
    expect(within(indicators).getByText("Claims")).toBeVisible();
    expect(within(indicators).getByText("Revisões pendentes")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Investigações recentes" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Claims que exigem atenção" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Estado efetivo da Evidence" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Atividade recente" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Contradições abertas" })).toBeVisible();
    expect(screen.getByText(/isso não torna a Claim falsa/i)).toBeVisible();
    expect(screen.getByText(/sem score, fonte real ou inferência de risco/i)).toBeVisible();
  });

  it("renders an explicit empty dashboard without fabricating activity", async () => {
    renderPage("empty");

    expect(await screen.findByText("Nenhum dado no cenário atual")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Atividade recente" })).not.toBeInTheDocument();
  });

  it("reports fixture read failures without suggesting a backend request", async () => {
    renderPage("error");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a Visão Geral",
    );
    expect(screen.getByText(/Nenhum serviço externo foi consultado/i)).toBeVisible();
  });
});
