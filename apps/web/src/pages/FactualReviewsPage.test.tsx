import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { FixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import { FactualReviewDetailPage } from "./FactualReviewDetailPage";
import { FactualReviewsPage } from "./FactualReviewsPage";

afterEach(cleanup);

describe("Factual review views", () => {
  it("shows every effective F5.4 state in a read-only queue", async () => {
    render(
      <MemoryRouter>
        <FactualReviewsPage dataSource={new FixtureIntelligenceDataSource()} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Fila somente leitura/i)).toBeVisible();
    for (const label of [
      "Revisão pendente",
      "Aceita para uso factual interno",
      "Rejeitada para uso factual interno",
      "Requer correção",
      "Decisão invalidada",
    ]) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    }
    expect(
      screen.queryByRole("button", { name: /aceitar|rejeitar|invalidar/i }),
    ).not.toBeInTheDocument();
  });

  it("shows the exact review basis and invalidation reason without mutation actions", async () => {
    render(
      <MemoryRouter initialEntries={["/revisoes/review-02"]}>
        <Routes>
          <Route
            path="/revisoes/:reviewId"
            element={<FactualReviewDetailPage dataSource={new FixtureIntelligenceDataSource()} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", {
        name: "Identificador anterior permanece aplicável à entidade",
      }),
    ).toBeVisible();
    expect(
      screen.getByText("A Evidence exata vinculada recebeu estado efetivo Revogado."),
    ).toBeVisible();
    expect(screen.getByText(/Claim v1/)).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
