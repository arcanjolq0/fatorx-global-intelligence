import { createBrowserRouter } from "react-router";
import type { RouteObject } from "react-router";

import { AppLayout } from "../components/layout/AppLayout";
import { AuditPage } from "../pages/AuditPage";
import { DashboardPage } from "../pages/DashboardPage";
import { EntitiesPage } from "../pages/EntitiesPage";
import { EntityConfirmationPage } from "../pages/EntityConfirmationPage";
import { ClaimDetailPage } from "../pages/ClaimDetailPage";
import { ClaimsPage } from "../pages/ClaimsPage";
import { EvidenceExplorerPage } from "../pages/EvidenceExplorerPage";
import { FactualReviewDetailPage } from "../pages/FactualReviewDetailPage";
import { FactualReviewsPage } from "../pages/FactualReviewsPage";
import { InvestigationDetailPage } from "../pages/InvestigationDetailPage";
import { InvestigationsPage } from "../pages/InvestigationsPage";
import { NewInvestigationPage } from "../pages/NewInvestigationPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ReportsPage } from "../pages/ReportsPage";
import { SettingsPage } from "../pages/SettingsPage";
import { SourcesPage } from "../pages/SourcesPage";
import { appRoutes } from "./navigation";
import type { AppRouteId } from "./navigation";

function getRouteElement(routeId: AppRouteId) {
  switch (routeId) {
    case "overview":
      return <DashboardPage />;
    case "investigations":
      return <InvestigationsPage />;
    case "new-investigation":
      return <NewInvestigationPage />;
    case "entity-confirmation":
      return <EntityConfirmationPage />;
    case "investigation-detail":
      return <InvestigationDetailPage />;
    case "entities":
      return <EntitiesPage />;
    case "evidence":
      return <EvidenceExplorerPage />;
    case "claims":
      return <ClaimsPage />;
    case "claim-detail":
      return <ClaimDetailPage />;
    case "reviews":
      return <FactualReviewsPage />;
    case "review-detail":
      return <FactualReviewDetailPage />;
    case "sources":
      return <SourcesPage />;
    case "reports":
      return <ReportsPage />;
    case "audit":
      return <AuditPage />;
    case "settings":
      return <SettingsPage />;
  }
}

const applicationRoutes: RouteObject[] = appRoutes.map((route) =>
  route.path === "/"
    ? { index: true, element: getRouteElement(route.id) }
    : {
        path: route.path.slice(1),
        element: getRouteElement(route.id),
      },
);

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [...applicationRoutes, { path: "*", element: <NotFoundPage /> }],
  },
]);
