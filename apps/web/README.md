# Web

Frontend do Fator X Global Intelligence em React, TypeScript e Vite. A foundation contém navegação, shell responsivo, design tokens, componentes reutilizáveis e uma fronteira de leitura alimentada exclusivamente por fixtures sintéticas tipadas.

## Estrutura

- `src/app`: configuração única de navegação e router.
- `src/components/layout`: shell, sidebar clara, cabeçalho, breadcrumbs e busca visual.
- `src/components/ui`: primitives acessíveis de interface.
- `src/data`: read models de apresentação, porta assíncrona de leitura e adapter de fixtures.
- `src/workflow`: porta separada de comandos do fluxo e adapter sintético local.
- `src/pages`: fluxo inicial de investigação, placeholders explícitos e página 404.

## Rotas

As rotas `/investigacoes`, `/investigacoes/nova`, `/investigacoes/nova/confirmacao` e `/investigacoes/:investigationId` formam o primeiro fluxo navegável. Busca e confirmação preservam o identificador na URL; o detalhe preserva a seção ativa em query string. As demais rotas da aplicação continuam navegáveis com placeholders explícitos.

A busca global permanece somente visual e read-only. A busca da listagem e o fluxo de criação operam exclusivamente sobre fixtures. Nenhum componente chama endpoint, persiste investigação, consulta fonte, calcula risco ou gera relatório.

## Fronteira de dados

`IntelligenceDataSource` define apenas leituras assíncronas para dashboard, investigações, detalhe, Evidence, Claims, revisões factuais e atividade. `FixtureIntelligenceDataSource` implementa essa porta com cenários `populated`, `empty` e `error`; cenários são selecionados por injeção em desenvolvimento/teste e não possuem controles na UI produtiva.

Os tipos são read models do frontend, não espelhos do domínio Python. Em Claims, elegibilidade contextual F5.2, admissibilidade global F5.3 e revisão factual F5.4 são campos e tipos distintos, com suas finalidades explícitas. Todos os nomes e identificadores das fixtures são sintéticos.

## Fronteira de comandos

`InvestigationWorkflow` expõe somente `searchEntityCandidates`, `createInvestigation` e `confirmEntity`. `FixtureInvestigationWorkflow` implementa esses comandos de forma determinística e local para demonstração. Ele não reutiliza a porta de read models, não usa `fetch` e pode ser substituído no futuro por um adapter HTTP somente quando um contrato real for aprovado.

## Desenvolvimento e verificações

Execute a partir da raiz:

```bash
pnpm web:dev
pnpm --filter @fatorx/web lint
pnpm --filter @fatorx/web format:check
pnpm --filter @fatorx/web typecheck
pnpm --filter @fatorx/web test
pnpm --filter @fatorx/web build
```
