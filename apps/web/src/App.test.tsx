import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the initial accessible application shell", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { level: 1, name: "Fator X Global Intelligence" }),
    ).toBeVisible();
    expect(screen.getByText("Fase inicial")).toBeVisible();
    expect(screen.getByRole("status", { name: "Estado atual do sistema" })).toHaveTextContent(
      "Os recursos de investigação ainda não foram habilitados.",
    );
    const skipLink = screen.getByRole("link", { name: "Ir para o conteúdo principal" });
    expect(skipLink).toHaveAttribute("href", "#main-content");
    skipLink.focus();
    expect(skipLink).toHaveFocus();
    expect(document.querySelector("main")).toHaveAttribute("id", "main-content");
  });
});
