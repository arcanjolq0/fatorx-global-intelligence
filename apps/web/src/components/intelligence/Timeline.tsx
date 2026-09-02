import type { ReactNode } from "react";

export interface TimelineEntry {
  readonly id: string;
  readonly meta?: ReactNode;
  readonly occurredAt: string;
  readonly title: ReactNode;
}

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

export function Timeline({
  emptyLabel = "Nenhuma atividade sintética registrada.",
  entries,
}: {
  readonly emptyLabel?: string;
  readonly entries: readonly TimelineEntry[];
}) {
  if (entries.length === 0) return <p className="empty-inline">{emptyLabel}</p>;

  return (
    <ol className="timeline">
      {entries.map((entry) => (
        <li key={entry.id}>
          <strong>{entry.title}</strong>
          {entry.meta === undefined ? null : <span className="timeline__meta">{entry.meta}</span>}
          <time dateTime={entry.occurredAt}>
            {dateFormatter.format(new Date(entry.occurredAt))}
          </time>
        </li>
      ))}
    </ol>
  );
}
