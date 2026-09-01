import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import { FixtureInvestigationWorkflow } from "../workflow/fixtures/FixtureInvestigationWorkflow";
import { NewInvestigationPage } from "./NewInvestigationPage";

function LocationProbe() {
  const location = useLocation();
  return <p>{`${location.pathname}${location.search}`}</p>;
}

function renderPage(workflow = new FixtureInvestigationWorkflow(), entry = "/investigacoes/nova") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/investigacoes/nova" element={<NewInvestigationPage workflow={workflow} />} />
        <Route path="/investigacoes/nova/confirmacao" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

function submitSearchForm() {
  const form = screen.getByRole("searchbox").closest("form");
  if (form === null) throw new Error("O campo de busca deve pertencer ao formulário.");
  fireEvent.submit(form);
}

afterEach(cleanup);

describe("NewInvestigationPage", () => {
  it("validates locally and returns focus to the identifier field", () => {
    renderPage();
    const input = screen.getByRole("searchbox", {
      name: /Empresa, documento, domínio, telefone ou outro identificador/i,
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar candidatos" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Informe ao menos um identificador");
    expect(input).toHaveFocus();
  });

  it("searches candidates and navigates with recoverable URL state", async () => {
    renderPage();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Atlas Meridian" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar candidatos" }));

    expect(
      await screen.findByText("/investigacoes/nova/confirmacao?identifier=Atlas+Meridian"),
    ).toBeVisible();
  });

  it("renders no-candidates and error recovery states", async () => {
    const { unmount } = renderPage(new FixtureInvestigationWorkflow({ scenario: "empty" }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Empresa teste" } });
    submitSearchForm();
    expect(await screen.findByText("Nenhum candidato encontrado")).toBeVisible();
    unmount();

    renderPage(new FixtureInvestigationWorkflow({ scenario: "error" }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Empresa teste" } });
    submitSearchForm();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível buscar candidatos",
    );
  });

  it("shows a non-network loading state", () => {
    renderPage(new FixtureInvestigationWorkflow({ delayMs: 10_000 }));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Atlas" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar candidatos" }));
    expect(screen.getByLabelText("Buscando candidatos sintéticos")).toBeVisible();
    expect(screen.getByRole("button", { name: /Buscar candidatos/ })).toBeDisabled();
  });
});
