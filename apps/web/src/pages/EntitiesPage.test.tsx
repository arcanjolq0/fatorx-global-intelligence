import { MemoryRouter } from "react-router";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EntitiesPage } from "./EntitiesPage";

describe("EntitiesPage", () => {
  it("keeps entity access contextual and points to a real route", () => {
    render(
      <MemoryRouter>
        <EntitiesPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", { level: 2, name: "Entidades vinculadas às investigações" }),
    ).toBeVisible();
    expect(
      screen.getByText("Não existe catálogo empresarial global nesta interface."),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Ver investigações" })).toHaveAttribute(
      "href",
      "/investigacoes",
    );
  });
});
