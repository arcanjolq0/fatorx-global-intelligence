import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  FixtureIntelligenceDataSource,
  type FixtureScenario,
} from "../data/fixtures/FixtureIntelligenceDataSource";
import { SourcesPage } from "./SourcesPage";

function renderPage(scenario: FixtureScenario = "populated") {
  return render(<SourcesPage dataSource={new FixtureIntelligenceDataSource({ scenario })} />);
}

afterEach(cleanup);

describe("SourcesPage", () => {
  it("labels every source as controlled TEST data and states its limitations", async () => {
    renderPage();

    const table = await screen.findByRole("table", { name: "Fontes sintéticas controladas" });
    expect(within(table).getAllByRole("row")).toHaveLength(5);
    expect(within(table).getAllByText("TEST · fixture controlada")).toHaveLength(3);
    expect(within(table).getByText("TEST · suspensa")).toBeVisible();
    expect(screen.getByText("Nenhuma fonte real está habilitada ou aprovada.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /adicionar fonte/i })).not.toBeInTheDocument();
  });

  it("renders an empty controlled catalog without promising discovery", async () => {
    renderPage("empty");

    expect(await screen.findByText("Nenhuma fonte controlada disponível")).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
