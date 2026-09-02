import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  FixtureIntelligenceDataSource,
  type FixtureScenario,
} from "../data/fixtures/FixtureIntelligenceDataSource";
import { ReportsPage } from "./ReportsPage";

function renderPage(scenario: FixtureScenario = "populated") {
  return render(<ReportsPage dataSource={new FixtureIntelligenceDataSource({ scenario })} />);
}

afterEach(cleanup);

describe("ReportsPage", () => {
  it("renders a preview-only report with an explicit factual trace", async () => {
    renderPage();

    expect(await screen.findByText("Esta prévia não é um relatório produtivo.")).toBeVisible();
    expect(screen.getByText("Prévia disponível")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Relatório → Claim → revisão factual → Evidence" }),
    ).toBeVisible();
    expect(
      screen.getByText("Denominação registrada corresponde a Atlas Meridian Comércio S.A."),
    ).toBeVisible();
    expect(screen.getAllByText("Aceita para uso factual interno")).toHaveLength(2);
    expect(screen.getByText("EVD-ATL-002")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /exportar|gerar|aprovar|assinar/i }),
    ).not.toBeInTheDocument();
  });

  it("shows unavailability when an investigation has no accepted factual claim", async () => {
    renderPage();
    const select = await screen.findByLabelText("Investigação da prévia");

    fireEvent.change(select, { target: { value: "inv-northstar-components" } });

    expect(screen.getByText("Prévia indisponível")).toBeVisible();
    expect(screen.getByText("Sem base factual aceita para a prévia")).toBeVisible();
    expect(screen.getByText(/não é uma conclusão sobre a entidade/i)).toBeVisible();
  });

  it("renders an empty preview state without generating anything", async () => {
    renderPage("empty");

    expect(await screen.findByText("Nenhuma prévia de relatório disponível")).toBeVisible();
    expect(screen.getByText(/Nenhum relatório foi gerado ou solicitado/i)).toBeVisible();
  });
});
