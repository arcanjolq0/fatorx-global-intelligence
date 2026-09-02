import { Icon } from "../icons/Icon";

export function GlobalSearch() {
  return (
    <div className="global-search">
      <label className="sr-only" htmlFor="global-search">
        Busca global
      </label>
      <Icon name="search" />
      <input
        aria-describedby="global-search-status"
        disabled
        id="global-search"
        placeholder="Buscar empresas, investigações, evidências..."
        type="search"
      />
      <span className="global-search__shortcut" aria-hidden="true">
        Indisponível
      </span>
      <span className="sr-only" id="global-search-status">
        Busca global indisponível nesta demonstração; nenhum serviço é consultado.
      </span>
    </div>
  );
}
