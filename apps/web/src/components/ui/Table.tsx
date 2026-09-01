import type { ReactNode } from "react";

import { StatePanel } from "./StatePanel";

export interface TableColumn<Row> {
  readonly align?: "left" | "right";
  readonly cell: (row: Row) => ReactNode;
  readonly header: string;
  readonly id: string;
  readonly mobileLabel?: string;
}

export interface TableProps<Row> {
  readonly caption: string;
  readonly columns: readonly TableColumn<Row>[];
  readonly emptyDescription?: string;
  readonly emptyTitle?: string;
  readonly getRowKey: (row: Row) => string;
  readonly rows: readonly Row[];
}

export function Table<Row>({
  caption,
  columns,
  emptyDescription = "A tabela ainda não possui registros para exibir.",
  emptyTitle = "Nenhum registro encontrado",
  getRowKey,
  rows,
}: TableProps<Row>) {
  if (rows.length === 0) {
    return (
      <StatePanel kind="empty" title={emptyTitle}>
        {emptyDescription}
      </StatePanel>
    );
  }

  return (
    <div aria-label={caption} className="table-region" role="region" tabIndex={0}>
      <table className="table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                className={column.align === "right" ? "align-right" : undefined}
                key={column.id}
                scope="col"
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => (
                <td
                  className={column.align === "right" ? "align-right" : undefined}
                  data-label={column.mobileLabel ?? column.header}
                  key={column.id}
                >
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
