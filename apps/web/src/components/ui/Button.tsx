import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly children: ReactNode;
  readonly variant?: ButtonVariant;
  readonly isLoading?: boolean;
}

export function Button({
  children,
  className = "",
  disabled = false,
  isLoading = false,
  type = "button",
  variant = "primary",
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      aria-busy={isLoading || undefined}
      className={`button button--${variant} ${className}`.trim()}
      disabled={disabled || isLoading}
      type={type}
    >
      {isLoading ? <span className="button__spinner" aria-hidden="true" /> : null}
      <span>{children}</span>
      {isLoading ? <span className="sr-only">Carregando</span> : null}
    </button>
  );
}
