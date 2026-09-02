import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Table } from "./Table";
import type { TableColumn } from "./Table";

interface Row {
  readonly id: string;
  readonly label: string;
  readonly status: string;
}

const columns: readonly TableColumn<Row>[] = [
  { id: "label", header: "Registro", cell: (row) => row.label },
  { id: "status", header: "Estado", cell: (row) => row.status },
];

describe("Table", () => {
  it("renders a semantic empty state", () => {
    render(
      <Table
        caption="Registros controlados"
        columns={columns}
        getRowKey={(row) => row.id}
        rows={[]}
      />,
    );

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nenhum registro encontrado" })).toBeVisible();
  });

  it("adds mobile labels while preserving table semantics", () => {
    render(
      <Table
        caption="Registros controlados"
        columns={columns}
        getRowKey={(row) => row.id}
        rows={[{ id: "1", label: "Item controlado", status: "Indisponível" }]}
      />,
    );

    expect(screen.getByRole("table", { name: "Registros controlados" })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Registro" })).toBeVisible();
    expect(screen.getByRole("cell", { name: "Item controlado" })).toHaveAttribute(
      "data-label",
      "Registro",
    );
  });
});
