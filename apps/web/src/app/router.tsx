import { createBrowserRouter } from "react-router";
import type { RouteObject } from "react-router";

import { AppLayout } from "../components/layout/AppLayout";
import { InvestigationsPage } from "../pages/InvestigationsPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { appRoutes } from "./navigation";

const foundationRoutes: RouteObject[] = appRoutes.map((route) =>
  route.path === "/"
    ? { index: true, element: <PlaceholderPage route={route} /> }
    : {
        path: route.path.slice(1),
        element:
          route.id === "investigations" ? (
            <InvestigationsPage />
          ) : (
            <PlaceholderPage route={route} />
          ),
      },
);

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [...foundationRoutes, { path: "*", element: <NotFoundPage /> }],
  },
]);
