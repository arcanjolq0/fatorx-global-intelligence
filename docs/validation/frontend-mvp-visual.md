# Validação visual do Frontend MVP

- Data: 2026-09-02
- Branch: `frontend-mvp`
- Baseline inicial: `635722a`
- Escopo: finalização visual e experiência demonstrativa do frontend

## Escopo revisado

Foram revisadas as seguintes rotas e seus estados visuais:

- `/`;
- `/investigacoes`;
- `/investigacoes/nova`;
- `/investigacoes/nova/confirmacao`;
- `/investigacoes/:investigationId`;
- `/entidades`;
- `/evidencias`;
- `/claims`;
- `/claims/:claimId`;
- `/revisoes`;
- `/revisoes/:reviewId`;
- `/fontes`;
- `/relatorios`;
- `/auditoria`;
- `/configuracoes`;
- rota não reconhecida (`404`).

A revisão cobriu hierarquia de títulos, breadcrumbs, navegação ativa, links de retorno,
deep links, tabelas, cards, badges, filtros, estados vazios/carregamento/erro e textos em
português do Brasil. O placeholder técnico remanescente de foundation foi removido.

## Direção visual

A interface mantém o shell claro de Enterprise Intelligence / Investigation Workspace:

- sidebar fixa em desktop e drawer em telas menores;
- topbar com busca global visualmente destacada e explicitamente indisponível;
- superfícies claras, bordas suaves, sombras discretas e espaço em branco consistente;
- cor reservada para hierarquia, estados e alertas sem uso decorativo excessivo;
- densidade equilibrada entre leitura executiva e rastreabilidade investigativa.

## Fronteira de mocks e fixtures

- `FixtureIntelligenceDataSource` continua sendo o único adaptador de leitura da interface.
- `FixtureInvestigationWorkflow` continua sendo a fronteira local do fluxo demonstrativo.
- A busca global está desabilitada e não dispara chamadas.
- A busca da nova investigação opera apenas sobre candidatos sintéticos locais.
- Fontes são canais controlados em modo `TEST`; não representam acesso, licença, cobertura ou
  catálogo produtivo G6.
- Auditoria é uma projeção local somente leitura e sem payloads sensíveis.
- Relatórios são apenas prévias visuais; não há geração, PDF, exportação, assinatura, score ou
  decisão de crédito.
- Configurações apenas descreve o estado local. Nenhuma preferência, autenticação, permissão ou
  integração é persistida.

Não foram adicionados endpoint, cliente HTTP, segredo, dependência, autenticação, notificação,
fonte real, risk engine ou alteração de backend.

## Dependências futuras de API

As portas tipadas `IntelligenceDataSource` e `InvestigationWorkflow` preservam a separação para
uma integração futura. Nenhuma URL ou contrato HTTP foi presumido. Busca global, persistência de
preferências, catálogo empresarial, fontes reais, auditoria persistida e exportação de relatórios
dependem de fases e contratos ainda não autorizados.

## Responsividade e navegação

A inspeção no navegador local cobriu 1440 × 1000, 1024 × 900, 768 × 900 e 390 × 844. Todas as
16 rotas acima foram verificadas nos breakpoints relevantes, sem overflow horizontal do documento
e sem links vazios ou com destino `#`.

Em telas menores:

- tabelas adotam apresentação em cards com rótulos por célula e quebra de texto;
- filtros e grids passam para uma coluna quando necessário;
- tabs mantêm rolagem horizontal contida;
- sidebar funciona como drawer modal, fecha com `Escape`, contém o foco e o devolve ao acionador;
- o scroll do documento é bloqueado somente enquanto o drawer está aberto.

## Acessibilidade

- um único `h1` contextual por rota, seguido por hierarquia de conteúdo;
- skip link para o conteúdo principal e foco movido ao `main` em mudanças de rota;
- foco visível global e estados ativos que não dependem apenas de cor;
- alvos de botões visíveis com pelo menos 44 px nos cenários móveis inspecionados;
- labels associados a campos e contagens dinâmicas anunciadas com `aria-live`;
- Dialog existente preserva foco inicial, trap, `Escape` e restauração;
- drawer móvel possui semântica modal, trap, `Escape` e restauração;
- tabelas preservam caption e região navegável no desktop, além de rótulos no mobile;
- `prefers-reduced-motion` reduz animações e transições;
- contraste textual dos tokens principais supera 4,5:1; bordas fortes de controles superam 3:1
  sobre branco.

## Limitações conhecidas

- Todos os dados de negócio são sintéticos e locais.
- Alterações do fluxo demonstrativo não persistem após a sessão.
- A busca global é apenas composição visual e permanece desabilitada.
- A rota de entidades não oferece catálogo global; direciona ao contexto de cada investigação.
- O histórico agregado da investigação não está disponível além dos eventos sintéticos exibidos
  nas vistas especializadas.
- Não há autenticação, gestão de usuários, permissões aplicadas, notificações ou preferências
  persistidas.
- Não há fonte real, catálogo G6, risk score, relatório produtivo ou integração de backend.

## Gates de qualidade

| Gate                | Resultado                                                  |
| ------------------- | ---------------------------------------------------------- |
| `pnpm test`         | PASS — 1.650 testes Python e 61 testes web                 |
| Cobertura Python    | PASS — 90,06% total                                        |
| `pnpm lint`         | PASS — Ruff, ESLint e scanner de segredos                  |
| `pnpm format`       | PASS — 241 arquivos Python inalterados e Prettier aplicado |
| `pnpm format:check` | PASS                                                       |
| `pnpm typecheck`    | PASS — mypy em 240 arquivos e TypeScript                   |
| `pnpm build`        | PASS — pacotes Python e bundle web                         |
| `git diff --check`  | PASS                                                       |

A primeira chamada de `pnpm test` foi recusada corretamente pelo guard dos testes destrutivos
porque a variável de consentimento não estava definida. Após confirmar o alvo dedicado local
`127.0.0.1:55432/fatorx_test` e o container saudável, o gate foi repetido com consentimento
restrito ao processo e passou integralmente. Os 16 warnings SQLAlchemy observados são os mesmos
avisos de reflection/migration já presentes na baseline; não foram ocultados.

## Correções após revisão independente

- Resultado da revisão independente: `APPROVED_WITH_FIXES`.
- `FRONTEND-REVIEW-001` foi corrigido: o foco de rota continua no `main`, agora com
  `preventScroll`; carregamento inicial e navegação direta iniciam no topo, enquanto uma
  navegação `POP` preserva a posição restaurada pelo histórico do navegador.
- `FRONTEND-REVIEW-002` foi corrigido: em telas móveis a busca global segue desabilitada, exibe
  visivelmente `Indisponível` e usa uma aparência de campo indisponível, sem navegação ou chamada
  de rede.
- Foram incluídos testes DOM determinísticos para a política de foco/scroll, retorno pelo
  histórico, disponibilidade do shell em 390 px e 1440 px, e o estado indisponível da busca em
  390 px. A verificação visual local complementa esses testes para os estilos responsivos.
- Nenhum arquivo de backend foi alterado; não foram adicionados endpoint, busca produtiva ou nova
  integração.

A revisão final do frontend permanece pendente de rechecagem independente.

## Gates das correções de revisão

| Gate                                     | Resultado                                                            |
| ---------------------------------------- | -------------------------------------------------------------------- |
| Testes focados                           | PASS — 11 testes de rota, foco, histórico, menu e busca indisponível |
| `pnpm --filter @fatorx/web test`         | PASS — 67 testes web                                                 |
| `pnpm --filter @fatorx/web lint`         | PASS                                                                 |
| `pnpm --filter @fatorx/web format:check` | PASS                                                                 |
| `pnpm --filter @fatorx/web typecheck`    | PASS                                                                 |
| `pnpm --filter @fatorx/web build`        | PASS                                                                 |
| `git diff --check`                       | PASS                                                                 |
