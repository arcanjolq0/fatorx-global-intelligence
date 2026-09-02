import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SettingsPage } from "./SettingsPage";

describe("SettingsPage", () => {
  it("presents the local demo configuration without editable or productive actions", () => {
    render(<SettingsPage />);

    expect(
      screen.getByRole("heading", { level: 2, name: "Preferências e limites do workspace" }),
    ).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Workspace" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 2, name: "Preferências visuais" })).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 2, name: "Dados da sessão de demonstração" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { level: 2, name: "Capacidades indisponíveis" }),
    ).toBeVisible();
    expect(screen.getByText("Nenhuma alteração é salva.")).toBeVisible();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });
});
