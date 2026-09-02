import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { FixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import type { InvestigationDetail } from "../data/types";
import { InvestigationDetailPage } from "./InvestigationDetailPage";

class PendingDataSource extends FixtureIntelligenceDataSource {
  override getInvestigationDetail(): Promise<InvestigationDetail | null> {
    return new Promise(() => undefined);
  }
}

function renderPage(
  dataSource = new FixtureIntelligenceDataSource(),
  entry = "/investigacoes/inv-atlas-meridian",
) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route
          path="/investigacoes/:investigationId"
          element={<InvestigationDetailPage dataSource={dataSource} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(cleanup);

describe("InvestigationDetailPage", () => {
  it("renders populated overview without a risk score", async () => {
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Atlas Meridian Comércio S.A." }),
    ).toBeVisible();
    expect(screen.getAllByText("Aguardando revisão")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Atividade recente" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Evidências em destaque" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Contradições relevantes" })).toBeVisible();
    expect(screen.queryByText(/score de risco/i)).not.toBeInTheDocument();
  });

  it("navigates URL-backed tabs and differentiates fixture confirmation", async () => {
    renderPage();
    const entityTab = await screen.findByRole("link", { name: "Entidade" });
    fireEvent.click(entityTab);
    expect(await screen.findByText("Confirmada na fixture")).toBeVisible();
    expect(screen.getByText("Fixture sintética local")).toBeVisible();
    expect(entityTab).toHaveAttribute("href", "/investigacoes/inv-atlas-meridian?tab=entity");

    fireEvent.click(screen.getByRole("link", { name: "Evidências" }));
    expect(await screen.findByText("EVD-ATL-002")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Filtrar Evidence" })).toBeVisible();
    expect(screen.queryByText("EVD-NOR-001")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "Claims" }));
    expect(
      await screen.findByText("Denominação registrada corresponde a Atlas Meridian Comércio S.A."),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("link", { name: "Revisões" }));
    expect(
      await screen.findByText("Fila de revisões factuais somente leitura"),
    ).toBeInTheDocument();
  });

  it("renders not-found, loading and error states", async () => {
    const notFound = renderPage(new FixtureIntelligenceDataSource(), "/investigacoes/inexistente");
    expect(await screen.findByText("Investigação não encontrada")).toBeVisible();
    notFound.unmount();

    const loading = renderPage(new PendingDataSource());
    expect(screen.getByLabelText("Carregando detalhe da investigação")).toBeVisible();
    loading.unmount();

    renderPage(new FixtureIntelligenceDataSource({ scenario: "error" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível carregar a investigação",
    );
  });
});
