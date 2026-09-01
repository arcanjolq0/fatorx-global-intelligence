import { Link, useLocation } from "react-router";

import { getRouteBreadcrumbs, getRouteByPathname, notFoundRoute } from "../../app/navigation";
import { Icon } from "../icons/Icon";
import { Badge, Button } from "../ui";
import { GlobalSearch } from "./GlobalSearch";

export interface HeaderProps {
  readonly isSidebarOpen: boolean;
  readonly onMenuClick: () => void;
}

export function Header({ isSidebarOpen, onMenuClick }: HeaderProps) {
  const location = useLocation();
  const route = getRouteByPathname(location.pathname);
  const breadcrumbs = route === undefined ? [] : getRouteBreadcrumbs(route);
  const page = route ?? notFoundRoute;

  return (
    <div className="app-header">
      <header className="topbar" aria-label="Barra superior">
        <Button
          aria-controls="app-sidebar"
          aria-expanded={isSidebarOpen}
          aria-label={isSidebarOpen ? "Fechar menu" : "Abrir menu"}
          className="topbar__menu"
          onClick={onMenuClick}
          variant="ghost"
        >
          <Icon name={isSidebarOpen ? "x" : "menu"} />
        </Button>
        <GlobalSearch />
        <div className="topbar__status">
          <Badge tone="neutral">Sem integração</Badge>
        </div>
      </header>

      <div className="page-header">
        <nav aria-label="Breadcrumb" className="breadcrumbs">
          <ol>
            {breadcrumbs.map((breadcrumb, index) => {
              const isCurrent = index === breadcrumbs.length - 1;
              return (
                <li key={breadcrumb.id}>
                  {isCurrent ? (
                    <span aria-current="page">{breadcrumb.label}</span>
                  ) : (
                    <Link to={breadcrumb.path}>{breadcrumb.label}</Link>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>
        <p className="eyebrow">{page.eyebrow}</p>
        <h1>{page.title}</h1>
      </div>
    </div>
  );
}
