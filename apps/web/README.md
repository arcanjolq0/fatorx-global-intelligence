# Web

Frontend do Fator X Global Intelligence em React, TypeScript e Vite. A foundation contém navegação, shell responsivo, design tokens, componentes reutilizáveis e uma fronteira de leitura alimentada exclusivamente por fixtures sintéticas tipadas.

## Estrutura

- `src/app`: configuração única de navegação e router.
- `src/components/layout`: shell, sidebar clara, cabeçalho, breadcrumbs e busca visual.
- `src/components/ui`: primitives acessíveis de interface.
- `src/data`: read models de apresentação, porta assíncrona e adapter de fixtures.
- `src/pages`: listagem inicial de investigações, placeholders explícitos e página 404.

## Rotas

As rotas `/`, `/investigacoes`, `/investigacoes/nova`, `/investigacoes/:investigationId`, `/entidades`, `/evidencias`, `/claims`, `/revisoes`, `/fontes`, `/relatorios`, `/auditoria` e `/configuracoes` são navegáveis. Somente `/investigacoes` consome a fronteira tipada nesta entrega; o detalhe dinâmico e as demais páginas permanecem como placeholders.

A busca global permanece somente visual e read-only. A busca da listagem de investigações é local e opera sobre fixtures. Nenhum componente chama endpoint, cria investigação, consulta fonte, calcula risco ou gera relatório.

## Fronteira de dados

`IntelligenceDataSource` define apenas leituras assíncronas para dashboard, investigações, detalhe, Evidence, Claims, revisões factuais e atividade. `FixtureIntelligenceDataSource` implementa essa porta com cenários `populated`, `empty` e `error`; cenários são selecionados por injeção em desenvolvimento/teste e não possuem controles na UI produtiva.

Os tipos são read models do frontend, não espelhos do domínio Python. Em Claims, elegibilidade contextual F5.2, admissibilidade global F5.3 e revisão factual F5.4 são campos e tipos distintos, com suas finalidades explícitas. Todos os nomes e identificadores das fixtures são sintéticos.

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
