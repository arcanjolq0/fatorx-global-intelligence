import type { IconName } from "../components/icons/Icon";

export type AppRouteId =
  | "overview"
  | "investigations"
  | "new-investigation"
  | "entities"
  | "evidence"
  | "claims"
  | "reviews"
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
      "A estrutura da visão operacional está pronta; indicadores e atividade aguardam fixtures tipadas.",
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
      "O fluxo será construído sobre fixtures tipadas; esta rota não cria registros nem chama a API.",
    icon: "add",
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
      "O Evidence Explorer não faz parte desta entrega e nenhuma admissibilidade é inferida pela interface.",
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
      "Claims, vínculos e elegibilidade contextual permanecem fora da foundation e sem dados simulados.",
    icon: "claims",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "reviews",
    path: "/revisoes",
    label: "Revisões",
    title: "Revisões factuais",
    eyebrow: "Revisão humana",
    description:
      "Nenhuma decisão factual é exibida ou criada nesta etapa; a rota é somente estrutural.",
    icon: "reviews",
    group: "workspace",
    showInSidebar: true,
  },
  {
    id: "sources",
    path: "/fontes",
    label: "Fontes",
    title: "Fontes",
    eyebrow: "Cobertura e política",
    description:
      "Não existe catálogo aprovado nem fonte real habilitada; a interface não promete cobertura.",
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
      "Relatórios produtivos e exportação não existem no baseline e permanecem indisponíveis.",
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
      "A foundation não consulta eventos persistidos; filtros e projeções serão definidos posteriormente.",
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
  return appRoutes.find((route) => route.path === normalizedPath);
}

export function getRouteBreadcrumbs(route: AppRouteDefinition): readonly AppRouteDefinition[] {
  if (route.parentId === undefined) {
    return [route];
  }

  const parent = appRoutes.find((candidate) => candidate.id === route.parentId);
  return parent === undefined ? [route] : [parent, route];
}
