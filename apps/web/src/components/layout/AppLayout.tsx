import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation } from "react-router";

import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    mainRef.current?.focus();
  }, [location.pathname]);

  return (
    <div className="application-shell">
      <a className="skip-link" href="#main-content">
        Ir para o conteúdo principal
      </a>
      <Sidebar
        isOpen={isSidebarOpen}
        onNavigate={() => {
          setSidebarOpen(false);
        }}
      />
      {isSidebarOpen ? (
        <button
          aria-label="Fechar menu"
          className="sidebar-scrim"
          onClick={() => {
            setSidebarOpen(false);
          }}
          type="button"
        />
      ) : null}
      <div className="application-shell__content">
        <Header
          isSidebarOpen={isSidebarOpen}
          onMenuClick={() => {
            setSidebarOpen((current) => !current);
          }}
        />
        <main className="main-content" id="main-content" ref={mainRef} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
