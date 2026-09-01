import { createBrowserRouter } from "react-router";
import type { RouteObject } from "react-router";

import { AppLayout } from "../components/layout/AppLayout";
import { EntityConfirmationPage } from "../pages/EntityConfirmationPage";
import { InvestigationDetailPage } from "../pages/InvestigationDetailPage";
import { InvestigationsPage } from "../pages/InvestigationsPage";
import { NewInvestigationPage } from "../pages/NewInvestigationPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { appRoutes } from "./navigation";

const foundationRoutes: RouteObject[] = appRoutes.map((route) =>
  route.path === "/"
    ? { index: true, element: <PlaceholderPage route={route} /> }
    : {
        path: route.path.slice(1),
        element: (() => {
          if (route.id === "investigations") return <InvestigationsPage />;
          if (route.id === "new-investigation") return <NewInvestigationPage />;
          if (route.id === "entity-confirmation") return <EntityConfirmationPage />;
          if (route.id === "investigation-detail") return <InvestigationDetailPage />;
          return <PlaceholderPage route={route} />;
        })(),
      },
);

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [...foundationRoutes, { path: "*", element: <NotFoundPage /> }],
  },
]);
