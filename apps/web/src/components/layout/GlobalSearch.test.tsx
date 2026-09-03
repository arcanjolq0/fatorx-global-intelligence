import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import "../../styles.css";

import { GlobalSearch } from "./GlobalSearch";

describe("GlobalSearch", () => {
  it("keeps the mobile search visibly unavailable without navigation or network activity", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    window.history.replaceState({}, "", "/investigacoes");
    render(<GlobalSearch />);

    const input = screen.getByRole("searchbox", { name: "Busca global" });
    const unavailableIndicator = screen.getByText("Indisponível");
    expect(input).toBeDisabled();
    expect(unavailableIndicator).toBeVisible();
    expect(getComputedStyle(unavailableIndicator).display).not.toBe("none");
    expect(input).toHaveAttribute("aria-describedby", "global-search-status");

    fireEvent.click(input);
    expect(window.location.pathname).toBe("/investigacoes");
  });
});
