import { useEffect, useRef, useState } from "react";
import { Outlet, useLocation, useNavigationType } from "react-router";

import { Header } from "./Header";
import { focusRouteMainContent, shouldResetRouteScroll } from "./routeFocus";
import { Sidebar } from "./Sidebar";

export function AppLayout() {
  const [isSidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const navigationType = useNavigationType();
  const mainRef = useRef<HTMLElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const focusBeforeDrawerRef = useRef<HTMLElement | null>(null);
  const drawerWasOpenRef = useRef(false);
  const isInitialRouteRef = useRef(true);

  useEffect(() => {
    const resetScroll = shouldResetRouteScroll(navigationType, isInitialRouteRef.current);
    focusRouteMainContent(mainRef.current, resetScroll);
    isInitialRouteRef.current = false;
  }, [location.key, navigationType]);

  useEffect(() => {
    if (!isSidebarOpen) {
      if (drawerWasOpenRef.current) {
        focusBeforeDrawerRef.current?.focus();
      }
      drawerWasOpenRef.current = false;
      return;
    }

    drawerWasOpenRef.current = true;
    focusBeforeDrawerRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const sidebar = sidebarRef.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const getFocusableElements = () =>
      sidebar === null
        ? []
        : [
            ...sidebar.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), [tabindex="0"]',
            ),
          ];
    getFocusableElements()[0]?.focus();

    function handleDrawerKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setSidebarOpen(false);
        return;
      }
      if (event.key !== "Tab") return;

      const focusableElements = getFocusableElements();
      const firstElement = focusableElements[0];
      const lastElement = focusableElements.at(-1);
      if (firstElement === undefined || lastElement === undefined) return;

      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault();
        lastElement.focus();
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault();
        firstElement.focus();
      }
    }

    document.addEventListener("keydown", handleDrawerKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleDrawerKeyDown);
    };
  }, [isSidebarOpen]);

  return (
    <div className="application-shell">
      <a className="skip-link" href="#main-content">
        Ir para o conteúdo principal
      </a>
      <Sidebar
        isOpen={isSidebarOpen}
        onNavigate={() => {
          focusBeforeDrawerRef.current = null;
          setSidebarOpen(false);
        }}
        sidebarRef={sidebarRef}
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
