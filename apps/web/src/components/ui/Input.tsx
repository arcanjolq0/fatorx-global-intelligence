import { useId } from "react";
import type { InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  readonly error?: string;
  readonly helperText?: string;
  readonly label: string;
}

export function Input({ error, helperText, id, label, required, ...props }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const descriptionId =
    error === undefined && helperText === undefined ? undefined : `${inputId}-help`;

  return (
    <label className="field" htmlFor={inputId}>
      <span className="field__label">
        {label}
        {required ? <span className="field__required">Obrigatório</span> : null}
      </span>
      <input
        {...props}
        aria-describedby={descriptionId}
        aria-invalid={error === undefined ? undefined : true}
        id={inputId}
        required={required}
      />
      {error === undefined && helperText === undefined ? null : (
        <span
          className={error === undefined ? "field__helper" : "field__error"}
          id={descriptionId}
          role={error === undefined ? undefined : "alert"}
        >
          {error ?? helperText}
        </span>
      )}
    </label>
  );
}
