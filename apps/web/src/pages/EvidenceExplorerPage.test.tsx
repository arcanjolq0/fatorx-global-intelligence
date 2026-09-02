import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import { FixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type { InvestigationSummary } from "../data/types";
import { EvidenceExplorerPage } from "./EvidenceExplorerPage";

class PendingDataSource extends FixtureIntelligenceDataSource {
  override listInvestigations(): Promise<readonly InvestigationSummary[]> {
    return new Promise(() => undefined);
  }
}

function renderPage(dataSource = new FixtureIntelligenceDataSource()) {
  return render(
    <MemoryRouter>
      <EvidenceExplorerPage dataSource={dataSource} />
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("EvidenceExplorerPage", () => {
  it("shows every effective F5.3 state separately from the persisted state", async () => {
    renderPage();
    expect(await screen.findByText("EVD-ATL-002")).toBeVisible();
    for (const label of [
      "Pendente",
      "Admissível para uso factual interno",
      "Restrita",
      "Rejeitada",
      "Expirada",
      "Revogada",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(screen.getAllByText("PENDING").length).toBeGreaterThan(0);
    expect(screen.getByText(/campo persistido permanece PENDING/i)).toBeVisible();
  });

  it("filters locally and distinguishes filtered-empty from data-empty", async () => {
    renderPage();
    await screen.findByText("EVD-ATL-002");
    fireEvent.change(screen.getByLabelText("Admissibilidade efetiva"), {
      target: { value: "REVOKED" },
    });
    expect(screen.getByText("EVD-ATL-001")).toBeVisible();
    expect(screen.queryByText("EVD-NOR-001")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Busca local"), {
      target: { value: "sem correspondencia" },
    });
    expect(screen.getByText("Nenhuma Evidence corresponde aos filtros")).toBeVisible();

    cleanup();
    renderPage(new FixtureIntelligenceDataSource({ scenario: "empty" }));
    expect(await screen.findByText("Nenhuma Evidence disponível")).toBeVisible();
  });

  it("renders an explicit adapter error", async () => {
    renderPage(new FixtureIntelligenceDataSource({ scenario: "error" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar os dados",
    );
  });

  it("announces the local loading state", () => {
    renderPage(new PendingDataSource());
    expect(screen.getByLabelText("Carregando Evidence Explorer")).toBeVisible();
  });
});
