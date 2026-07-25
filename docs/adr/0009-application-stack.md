# ADR-0009 — Stack inicial de aplicação

- Status: Accepted
- Data: 2026-07-25

## Contexto

O planejamento recomenda Python/FastAPI/Pydantic/SQLAlchemy/Alembic e React/TypeScript/Vite. No início da F1.1, o repositório ainda não possuía runtime, versões, lockfiles ou dependências analisadas.

## Decisão

Adotar um monorepo com as seguintes versões de referência para a Fase 1:

- Python 3.14.5, uv 0.11.13, FastAPI 0.140.0, Pydantic 2.13.4 e Uvicorn 0.51.0;
- Node.js 24.16.0, pnpm 11.5.2, React 19.2.8, TypeScript 6.0.3 e Vite 8.1.5;
- Ruff, mypy estrito, pytest e pytest-socket no backend;
- ESLint com regras tipadas, Prettier, Vitest e Testing Library no frontend;
- Hatchling para gerar wheel e source distribution Python;
- GitHub Actions como CI mínima, com ações fixadas por SHA.

As dependências diretas e suas versões completas ficam registradas em `docs/dependencies.md`; `uv.lock` e `pnpm-lock.yaml` são as fontes reproduzíveis de resolução. Python é suportado em `>=3.14,<3.15` e Node.js em `>=24.16.0,<25`, mas a CI usa os patches exatos acima.

TypeScript 6.0.3 foi escolhido em lugar do 7.0.2 por respeitar a faixa de compatibilidade declarada pelo `typescript-eslint` adotado. Python 3.14.5 foi mantido porque o uv 0.11.13 usado para criar o ambiente não ofereceu o artefato gerenciado 3.14.6 para Windows; a promoção de patch deve ocorrer em uma atualização deliberada da toolchain.

Nenhum cliente HTTP de produção, banco, fila/cache, biblioteca de componentes, SDK de IA ou integração externa é adotado nesta decisão. `HTTPX2` existe somente no grupo de desenvolvimento para o transporte ASGI em processo do `TestClient`. PostgreSQL continua sendo uma decisão futura regida pelo ADR-0007, fora da F1.1; a fila depende dos SLAs ainda pendentes.

## Evidências de aceitação

- versões suportadas e compatíveis estão nos manifests, `.python-version`, `.nvmrc` e CI;
- instalações congeladas foram validadas a partir dos dois lockfiles;
- finalidade, motivo, manutenção, licença e alternativa de cada dependência direta estão em `docs/dependencies.md`;
- comandos de lint, formatação, tipos, testes e build estão em `docs/development.md`;
- `pnpm quality` executa todos os gates localmente e na CI;
- nenhum SDK de fonte real ou componente da Fase 2 foi adicionado;
- a decisão de fila permanece adiada até a validação de SLA e operação.

## Consequências

A stack fica alinhada ao plano e adequada a contratos tipados, mas cria dois ecossistemas de build e dois lockfiles. A workflow de CI foi configurada para validar ambos; isso não representa uma execução no GitHub Actions. Um teste arquitetural impede dependências externas no pacote de domínio; os testes bloqueiam acesso de rede; e a introdução futura de qualquer dependência exige atualizar o registro.
