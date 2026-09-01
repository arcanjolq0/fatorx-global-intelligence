import { useId } from "react";
import type { SelectHTMLAttributes } from "react";

export interface SelectOption {
  readonly label: string;
  readonly value: string;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  readonly error?: string;
  readonly helperText?: string;
  readonly label: string;
  readonly options: readonly SelectOption[];
}

export function Select({ error, helperText, id, label, options, required, ...props }: SelectProps) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const descriptionId =
    error === undefined && helperText === undefined ? undefined : `${selectId}-help`;

  return (
    <label className="field" htmlFor={selectId}>
      <span className="field__label">
        {label}
        {required ? <span className="field__required">Obrigatório</span> : null}
      </span>
      <select
        {...props}
        aria-describedby={descriptionId}
        aria-invalid={error === undefined ? undefined : true}
        id={selectId}
        required={required}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
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
