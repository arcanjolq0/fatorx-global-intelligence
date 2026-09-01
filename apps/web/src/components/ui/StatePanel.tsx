import type { ReactNode } from "react";

import { Button } from "./Button";

export type StateKind = "empty" | "error" | "loading" | "unavailable";

export interface StatePanelProps {
  readonly actionLabel?: string;
  readonly children: ReactNode;
  readonly kind: StateKind;
  readonly onAction?: () => void;
  readonly title: string;
}

export function StatePanel({ actionLabel, children, kind, onAction, title }: StatePanelProps) {
  const liveRole = kind === "error" ? "alert" : kind === "loading" ? "status" : undefined;

  return (
    <section className={`state-panel state-panel--${kind}`} role={liveRole}>
      <div>
        <p className="eyebrow">{stateLabels[kind]}</p>
        <h3>{title}</h3>
        <div className="state-panel__content">{children}</div>
      </div>
      {actionLabel === undefined || onAction === undefined ? null : (
        <Button onClick={onAction} variant="secondary">
          {actionLabel}
        </Button>
      )}
    </section>
  );
}

const stateLabels: Readonly<Record<StateKind, string>> = {
  empty: "Sem dados",
  error: "Erro",
  loading: "Carregando",
  unavailable: "Indisponível nesta etapa",
};
