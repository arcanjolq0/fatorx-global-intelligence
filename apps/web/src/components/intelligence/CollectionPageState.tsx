import { Skeleton, StatePanel } from "../ui";

export function CollectionLoading({ label }: { readonly label: string }) {
  return (
    <div aria-busy="true" aria-label={label} className="collection-loading" role="status">
      <Skeleton height="8rem" />
      <Skeleton height="22rem" />
    </div>
  );
}

export function CollectionError({ onRetry }: { readonly onRetry: () => void }) {
  return (
    <StatePanel
      actionLabel="Tentar novamente"
      kind="error"
      onAction={onRetry}
      title="Não foi possível carregar os dados"
    >
      O adapter de fixtures falhou. Nenhum endpoint ou serviço externo foi consultado.
    </StatePanel>
  );
}
