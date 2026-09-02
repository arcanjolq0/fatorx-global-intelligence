import { createBrowserRouter } from "react-router";
import type { RouteObject } from "react-router";

import { AppLayout } from "../components/layout/AppLayout";
import { AuditPage } from "../pages/AuditPage";
import { DashboardPage } from "../pages/DashboardPage";
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
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { ReportsPage } from "../pages/ReportsPage";
import { SourcesPage } from "../pages/SourcesPage";
import { appRoutes } from "./navigation";

const foundationRoutes: RouteObject[] = appRoutes.map((route) =>
  route.path === "/"
    ? { index: true, element: <DashboardPage /> }
    : {
        path: route.path.slice(1),
        element: (() => {
          if (route.id === "investigations") return <InvestigationsPage />;
          if (route.id === "new-investigation") return <NewInvestigationPage />;
          if (route.id === "entity-confirmation") return <EntityConfirmationPage />;
          if (route.id === "investigation-detail") return <InvestigationDetailPage />;
          if (route.id === "evidence") return <EvidenceExplorerPage />;
          if (route.id === "claims") return <ClaimsPage />;
          if (route.id === "claim-detail") return <ClaimDetailPage />;
          if (route.id === "reviews") return <FactualReviewsPage />;
          if (route.id === "review-detail") return <FactualReviewDetailPage />;
          if (route.id === "sources") return <SourcesPage />;
          if (route.id === "reports") return <ReportsPage />;
          if (route.id === "audit") return <AuditPage />;
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
