# Web

Foundation do frontend do Fator X Global Intelligence em React, TypeScript e Vite. Esta camada implementa somente navegação, shell responsivo, design tokens e componentes reutilizáveis; não contém dados ou regras de negócio.

## Estrutura

- `src/app`: configuração única de navegação e router.
- `src/components/layout`: shell, sidebar clara, cabeçalho, breadcrumbs e busca visual.
- `src/components/ui`: primitives acessíveis de interface.
- `src/pages`: placeholders explícitos da foundation e página 404.

## Rotas

As rotas `/`, `/investigacoes`, `/investigacoes/nova`, `/entidades`, `/evidencias`, `/claims`, `/revisoes`, `/fontes`, `/relatorios`, `/auditoria` e `/configuracoes` são navegáveis. Todas exibem estado indisponível até a criação da fronteira de fixtures tipadas.

A busca global é somente visual e read-only. Nenhum componente chama endpoint, cria investigação, consulta fonte, calcula risco ou gera relatório.

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
