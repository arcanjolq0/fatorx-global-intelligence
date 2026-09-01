import { NavLink } from "react-router";

import { appRoutes, navigationGroups } from "../../app/navigation";
import type { NavigationGroup } from "../../app/navigation";
import { Icon } from "../icons/Icon";

export interface SidebarProps {
  readonly isOpen: boolean;
  readonly onNavigate: () => void;
}

const groupOrder: readonly NavigationGroup[] = ["workspace", "governance"];

export function Sidebar({ isOpen, onNavigate }: SidebarProps) {
  return (
    <aside
      className={`sidebar ${isOpen ? "sidebar--open" : ""}`}
      id="app-sidebar"
      aria-label="Navegação principal"
    >
      <div className="sidebar__brand">
        <span className="sidebar__mark" aria-hidden="true">
          FX
        </span>
        <span>
          <strong>Fator X</strong>
          <small>Global Intelligence</small>
        </span>
      </div>

      <nav className="sidebar__nav" aria-label="Módulos da aplicação">
        {groupOrder.map((group) => (
          <section className="sidebar__group" key={group} aria-labelledby={`nav-${group}`}>
            <h2 className="sidebar__label" id={`nav-${group}`}>
              {navigationGroups[group]}
            </h2>
            <div className="sidebar__links">
              {appRoutes
                .filter((route) => route.showInSidebar && route.group === group)
                .map((route) => (
                  <NavLink
                    className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`}
                    end={route.path === "/"}
                    key={route.id}
                    onClick={onNavigate}
                    to={route.path}
                  >
                    <Icon name={route.icon} />
                    <span>{route.label}</span>
                  </NavLink>
                ))}
            </div>
          </section>
        ))}
      </nav>

      <div className="sidebar__footer">
        <Icon name="shield" />
        <span>
          <strong>Foundation segura</strong>
          <small>Nenhum dado de negócio conectado</small>
        </span>
      </div>
    </aside>
  );
}
