import { fireEvent, render, screen } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";

import { Dialog } from "./Dialog";

function DialogHarness() {
  const [isOpen, setOpen] = useState(false);
  const initialFocusRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        onClick={() => {
          setOpen(true);
        }}
        type="button"
      >
        Abrir revisão
      </button>
      <Dialog
        initialFocusRef={initialFocusRef}
        isOpen={isOpen}
        onClose={() => {
          setOpen(false);
        }}
        title="Revisar item"
      >
        <button ref={initialFocusRef} type="button">
          Confirmar
        </button>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it("sets initial focus, traps tab navigation and restores focus on Escape", () => {
    render(<DialogHarness />);
    const trigger = screen.getByRole("button", { name: "Abrir revisão" });
    trigger.focus();
    fireEvent.click(trigger);

    const confirm = screen.getByRole("button", { name: "Confirmar" });
    const close = screen.getByRole("button", { name: "Fechar diálogo" });
    expect(confirm).toHaveFocus();
    expect(document.body).toHaveStyle({ overflow: "hidden" });

    fireEvent.keyDown(document, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();

    trigger.focus();
    expect(confirm).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.body).not.toHaveStyle({ overflow: "hidden" });
  });
});
