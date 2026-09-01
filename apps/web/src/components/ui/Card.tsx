import type { HTMLAttributes, ReactNode } from "react";

export interface CardProps extends HTMLAttributes<HTMLElement> {
  readonly children: ReactNode;
  readonly title?: string;
}

export function Card({ children, className = "", title, ...props }: CardProps) {
  return (
    <section {...props} className={`card ${className}`.trim()}>
      {title === undefined ? null : <h2 className="card__title">{title}</h2>}
      {children}
    </section>
  );
}
