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
        aria-disabled="true"
        id="global-search"
        placeholder="Buscar empresas, investigações, evidências..."
        readOnly
        type="search"
      />
      <span className="global-search__shortcut" aria-hidden="true">
        Em breve
      </span>
      <span className="sr-only" id="global-search-status">
        Busca disponível apenas como estrutura visual; nenhum endpoint é consultado.
      </span>
    </div>
  );
}
