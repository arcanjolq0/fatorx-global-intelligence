import type { IconName } from "../components/icons/Icon";

export type AppRouteId =
  | "overview"
  | "investigations"
  | "investigation-detail"
  | "new-investigation"
  | "entity-confirmation"
  | "entities"
  | "evidence"
  | "claims"
  | "claim-detail"
  | "reviews"
  | "review-detail"
  | "sources"
  | "reports"
  | "audit"
  | "settings";

export type NavigationGroup = "workspace" | "governance";

export interface AppRouteDefinition {
  readonly description: string;
  readonly eyebrow: string;
  readonly group: NavigationGroup;
  readonly icon: IconName;
  readonly id: AppRouteId;
  readonly label: string;
  readonly parentId?: AppRouteId;
  readonly path: string;
  readonly showInSidebar: boolean;
  readonly title: string;
}

export const navigationGroups: Readonly<Record<NavigationGroup, string>> = {
  workspace: "Workspace",
  governance: "Governança",
};

export const appRoutes = [
  {
    id: "overview",
    path: "/",
    label: "Visão Geral",
    title: "Visão Geral",
    eyebrow: "Workspace investigativo",
    description:
      "Indicadores operacionais derivados das fixtures tipadas, sem score ou inferência de risco.",
    icon: "overview",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "investigations",
    path: "/investigacoes",
    label: "Investigações",
    title: "Investigações",
    eyebrow: "Workspace investigativo",
    description:
      "A navegação está disponível, mas nenhuma investigação é listada ou consultada nesta foundation.",
    icon: "investigations",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "new-investigation",
    path: "/investigacoes/nova",
    label: "Nova investigação",
    title: "Nova investigação",
    eyebrow: "Fluxo de investigação",
    description:
      "Busca local em fixtures tipadas para iniciar o fluxo sem criar registros no backend.",
    icon: "add",
    group: "workspace",
    parentId: "investigations",
    showInSidebar: false,
  },
  {
    id: "entity-confirmation",
    path: "/investigacoes/nova/confirmacao",
    label: "Confirmação de entidade",
    title: "Confirmação de entidade",
    eyebrow: "Fluxo de investigação",
    description: "Seleção humana entre candidatos sintéticos, sem confirmar identidade no backend.",
    icon: "entities",
    group: "workspace",
    parentId: "new-investigation",
    showInSidebar: false,
  },
  {
    id: "investigation-detail",
    path: "/investigacoes/:investigationId",
    label: "Detalhe da investigação",
    title: "Detalhe da investigação",
    eyebrow: "Workspace investigativo",
    description:
      "Leitura sintética da investigação com identidade, resumo e limites factuais explícitos.",
    icon: "investigations",
    group: "workspace",
    parentId: "investigations",
    showInSidebar: false,
  },
  {
    id: "entities",
    path: "/entidades",
    label: "Entidades",
    title: "Entidades",
    eyebrow: "Resolução de identidade",
    description:
      "A foundation não consulta, confirma ou vincula entidades; a rota preserva esse limite explicitamente.",
    icon: "entities",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "evidence",
    path: "/evidencias",
    label: "Evidências",
    title: "Evidências",
    eyebrow: "Rastreabilidade",
    description:
      "Explore Evidence sintética e compare o estado persistido com a admissibilidade efetiva F5.3.",
    icon: "evidence",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "claims",
    path: "/claims",
    label: "Claims",
    title: "Claims",
    eyebrow: "Afirmações rastreáveis",
    description:
      "Claims sintéticas com vínculos explícitos, contradições e separação entre F5.2, F5.3 e F5.4.",
    icon: "claims",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "claim-detail",
    path: "/claims/:claimId",
    label: "Detalhe da Claim",
    title: "Detalhe da Claim",
    eyebrow: "Afirmação rastreável",
    description: "Versão exata da Claim, base de Evidence e histórico factual sintético.",
    icon: "claims",
    group: "workspace",
    parentId: "claims",
    showInSidebar: false,
  },
  {
    id: "reviews",
    path: "/revisoes",
    label: "Revisões",
    title: "Revisões factuais",
    eyebrow: "Revisão humana",
    description: "Fila somente leitura de decisões F5.4 sobre versões exatas de Claims sintéticas.",
    icon: "reviews",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "review-detail",
    path: "/revisoes/:reviewId",
    label: "Detalhe da revisão",
    title: "Detalhe da revisão factual",
    eyebrow: "Revisão humana",
    description: "Base, decisão e eventual invalidação da revisão factual sintética.",
    icon: "reviews",
    group: "workspace",
    parentId: "reviews",
    showInSidebar: false,
  },
  {
    id: "sources",
    path: "/fontes",
    label: "Fontes",
    title: "Fontes",
    eyebrow: "Cobertura e política",
    description:
      "Canais sintéticos controlados, suas limitações e cobertura exclusiva de demonstração.",
    icon: "sources",
    group: "governance",
    showInSidebar: true,
  },
  {
    id: "reports",
    path: "/relatorios",
    label: "Relatórios",
    title: "Relatórios",
    eyebrow: "Resultado investigativo",
    description:
      "Preview visual rastreável e não produtivo, sem geração, exportação ou decisão de risco.",
    icon: "reports",
    group: "governance",
    showInSidebar: true,
  },
  {
    id: "audit",
    path: "/auditoria",
    label: "Auditoria",
    title: "Auditoria",
    eyebrow: "Governança",
    description:
      "Projeção local somente leitura de eventos sintéticos, sem conteúdo bruto ou sensível.",
    icon: "audit",
    group: "governance",
    showInSidebar: true,
  },
  {
    id: "settings",
    path: "/configuracoes",
    label: "Configurações",
    title: "Configurações",
    eyebrow: "Workspace",
    description: "Nenhuma preferência, permissão ou integração é persistida por esta interface.",
    icon: "settings",
    group: "governance",
    showInSidebar: true,
  },
] as const satisfies readonly AppRouteDefinition[];

const appRoutesById = new Map<AppRouteId, AppRouteDefinition>(
  appRoutes.map((route) => [route.id, route]),
);

export const notFoundRoute = {
  id: "not-found",
  path: "*",
  label: "Página não encontrada",
  title: "Página não encontrada",
  eyebrow: "Navegação",
  description: "Este endereço não faz parte da foundation atual.",
} as const;

export function getRouteByPathname(pathname: string): AppRouteDefinition | undefined {
  const normalizedPath = pathname.length > 1 ? pathname.replace(/\/$/, "") : pathname;
  const exactRoute = appRoutes.find((route) => route.path === normalizedPath);
  if (exactRoute !== undefined) {
    return exactRoute;
  }

  return appRoutes.find((route) => {
    if (!route.path.includes(":")) {
      return false;
    }

    const routeSegments = route.path.split("/");
    const pathnameSegments = normalizedPath.split("/");
    return (
      routeSegments.length === pathnameSegments.length &&
      routeSegments.every(
        (segment, index) => segment.startsWith(":") || segment === pathnameSegments[index],
      )
    );
  });
}

export function getInvestigationDetailPath(investigationId: string): string {
  return `/investigacoes/${encodeURIComponent(investigationId)}`;
}

export function getClaimDetailPath(claimId: string): string {
  return `/claims/${encodeURIComponent(claimId)}`;
}

export function getReviewDetailPath(reviewId: string): string {
  return `/revisoes/${encodeURIComponent(reviewId)}`;
}

export function getEntityConfirmationPath(identifier: string): string {
  const searchParameters = new URLSearchParams({ identifier });
  return `/investigacoes/nova/confirmacao?${searchParameters.toString()}`;
}

export function getRouteBreadcrumbs(route: AppRouteDefinition): readonly AppRouteDefinition[] {
  const breadcrumbs: AppRouteDefinition[] = [route];
  let currentRoute: AppRouteDefinition = route;
  const visitedIds = new Set<AppRouteId>([route.id]);

  while (currentRoute.parentId !== undefined) {
    const parent = appRoutesById.get(currentRoute.parentId);
    if (parent === undefined || visitedIds.has(parent.id)) {
      break;
    }
    breadcrumbs.unshift(parent);
    visitedIds.add(parent.id);
    currentRoute = parent;
  }

  return breadcrumbs;
}
