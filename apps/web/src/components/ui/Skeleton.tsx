export interface SkeletonProps {
  readonly accessibleLabel?: string;
  readonly height?: string;
  readonly width?: string;
}

export function Skeleton({ accessibleLabel, height = "1rem", width = "100%" }: SkeletonProps) {
  return (
    <span
      aria-hidden={accessibleLabel === undefined ? true : undefined}
      className="skeleton"
      role={accessibleLabel === undefined ? undefined : "status"}
      style={{ height, width }}
    >
      {accessibleLabel === undefined ? null : <span className="sr-only">{accessibleLabel}</span>}
    </span>
  );
}
