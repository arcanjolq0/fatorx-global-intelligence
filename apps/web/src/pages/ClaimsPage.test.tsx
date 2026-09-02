import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { FixtureIntelligenceDataSource } from "../data/fixtures/FixtureIntelligenceDataSource";
import { ClaimDetailPage } from "./ClaimDetailPage";
import { ClaimsPage } from "./ClaimsPage";

afterEach(cleanup);

describe("Claims views", () => {
  it("keeps F5.2, F5.3 and F5.4 visibly separated and exposes all evidence roles", async () => {
    render(
      <MemoryRouter>
        <ClaimsPage dataSource={new FixtureIntelligenceDataSource()} />
      </MemoryRouter>,
    );
    expect(await screen.findByText(/ELIGIBLE não significa ADMISSIBLE/i)).toBeVisible();
    expect(screen.getAllByText("F5.2 · Elegibilidade contextual").length).toBeGreaterThan(0);
    expect(screen.getAllByText("F5.3 · Admissibilidade da Evidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText("F5.4 · Revisão factual da Claim").length).toBeGreaterThan(0);
    const roleSummaries = screen.getAllByLabelText("Papéis das evidências");
    expect(roleSummaries.some((item) => item.textContent.includes("1 contradiz(em)"))).toBe(true);
    expect(roleSummaries.some((item) => item.textContent.includes("1 qualifica(m)"))).toBe(true);
  });

  it("filters critical Claims without computing a score", async () => {
    render(
      <MemoryRouter>
        <ClaimsPage dataSource={new FixtureIntelligenceDataSource()} />
      </MemoryRouter>,
    );
    await screen.findByText("Situação cadastral permanece ativa no período observado");
    fireEvent.change(screen.getByLabelText("Criticidade"), { target: { value: "CRITICAL" } });
    expect(
      screen.getByText("Situação cadastral permanece ativa no período observado"),
    ).toBeVisible();
    expect(
      screen.queryByText("Denominação registrada corresponde a Atlas Meridian Comércio S.A."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/score de risco/i)).not.toBeInTheDocument();
  });

  it("renders exact-version Claim detail, history and qualifying evidence", async () => {
    render(
      <MemoryRouter initialEntries={["/claims/claim-northstar-registration-status"]}>
        <Routes>
          <Route
            path="/claims/:claimId"
            element={<ClaimDetailPage dataSource={new FixtureIntelligenceDataSource()} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", {
        name: "Situação cadastral permanece ativa no período observado",
      }),
    ).toBeVisible();
    expect(
      screen.getByText("ELIGIBLE ≠ ADMISSIBLE ≠ ACCEPTED FOR INTERNAL FACTUAL USE"),
    ).toBeVisible();
    expect(screen.getAllByText("Qualifica").length).toBeGreaterThan(0);
    expect(screen.getByText(/Versão 2 · Versão 2 adicionou vínculo contraditório/i)).toBeVisible();
  });
});
