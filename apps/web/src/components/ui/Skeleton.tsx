export interface SkeletonProps {
  readonly height?: string;
  readonly width?: string;
}

export function Skeleton({ height = "1rem", width = "100%" }: SkeletonProps) {
  return (
    <span className="skeleton" role="status" style={{ height, width }}>
      <span className="sr-only">Carregando</span>
    </span>
  );
}
