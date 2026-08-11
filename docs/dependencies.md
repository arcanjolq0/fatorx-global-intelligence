# Registro de dependências

## 1. Política

Este registro cobre todas as dependências diretas adicionadas. Versões foram consultadas nos registries oficiais em 25 de julho de 2026 e são fixadas nos manifests/lockfiles. Dependências transitivas são controladas pelos locks e devem ser revisadas quando mudarem.

Critérios comuns de manutenção: release estável disponível, repositório público ativo, compatibilidade declarada com o runtime e licença permissiva. Vulnerabilidade ou abandono futuro exige substituição ou aceite formal de risco.

## 2. Backend e ferramenta Python

| Dependência | Versão | Finalidade e motivo | Manutenção | Licença | Alternativa considerada |
|---|---:|---|---|---|---|
| FastAPI | 0.140.0 | API ASGI tipada exigida pelo plano; reduz código de contrato do endpoint. | Projeto ativo e versão recente no PyPI. | MIT | Starlette direto exigiria mais composição; Flask oferece menos integração tipada. |
| Pydantic | 2.13.4 | Schema explícito da resposta JSON e validação nas bordas futuras. Importado diretamente, portanto declarado diretamente. | Projeto ativo e base de tipos do FastAPI. | MIT | `dataclasses` + validação manual aumentariam código e divergência de schema. |
| Uvicorn | 0.51.0 | Servidor ASGI mínimo para desenvolvimento e smoke test local. | Projeto ativo do ecossistema ASGI. | BSD-3-Clause | Hypercorn é válido, mas não oferece benefício necessário nesta fase. |
| Hatchling | 1.31.0 | Backend PEP 517 pequeno para wheel/sdist reproduzíveis. | Projeto ativo da PyPA. | MIT | setuptools possui superfície/configuração maior; build sem backend não gera artefato padrão. |

## 3. Qualidade e testes Python

| Dependência | Versão | Finalidade e motivo | Manutenção | Licença | Alternativa considerada |
|---|---:|---|---|---|---|
| pytest | 9.1.1 | Runner legível, fixtures e integração com plugins de segurança/cobertura. | Projeto PyPA maduro e ativo. | MIT | `unittest` evitaria dependência, mas exigiria mais boilerplate e integração manual. |
| pytest-cov | 7.1.0 | Gate de cobertura com branch coverage. | Plugin pytest ativo. | MIT | `coverage run` separado duplicaria configuração/orquestração. |
| pytest-socket | 0.8.0 | Bloqueio objetivo de sockets durante testes. | Pacote mantido e compatível com Python 3.14. | MIT | monkeypatch manual teria cobertura incompleta e maior risco de bypass. |
| HTTPX2 | 2.9.1 | Transporte em processo recomendado pelo Starlette/FastAPI atual para o `TestClient`; declaração direta evita fallback descontinuado. | Projeto ativo e release estável no PyPI. | BSD-3-Clause | HTTPX 0.28.1 gera depreciação no FastAPI 0.140; chamadas manuais ao ASGI seriam mais frágeis. |
| mypy | 2.3.0 | Verificação estática estrita do backend e scripts. | Projeto maduro com releases regulares. | MIT | Pyright foi considerado; mypy mantém configuração Python central e simples. |
| Ruff | 0.16.0 | Lint e formatação em uma ferramenta rápida e com regras integradas. | Projeto ativo com releases frequentes. | MIT | Black + isort + Flake8 exigiriam três dependências e configurações. |

## 4. Runtime web

| Dependência | Versão | Finalidade e motivo | Manutenção | Licença | Alternativa considerada |
|---|---:|---|---|---|---|
| React | 19.2.8 | Biblioteca de UI exigida pelo planejamento. | Projeto ativo mantido pela equipe React. | MIT | Preact/vanilla reduziriam peso, mas divergiriam da decisão de stack. |
| React DOM | 19.2.8 | Renderer oficial do React no navegador. | Mantido e versionado com React. | MIT | Renderer próprio não é justificável. |

## 5. Build, tipos, lint e formatação web

| Dependência | Versão | Finalidade e motivo | Manutenção | Licença | Alternativa considerada |
|---|---:|---|---|---|---|
| Vite | 8.1.5 | Dev server e build web exigidos; configuração mínima. | Projeto ativo e versão estável atual. | MIT | Webpack exigiria mais configuração; scripts sem bundler não atendem ao build pedido. |
| `@vitejs/plugin-react` | 6.0.4 | Integra React ao pipeline Vite e Fast Refresh. | Plugin oficial do Vite. | MIT | Configuração Babel/Rolldown manual aumentaria superfície. |
| TypeScript | 6.0.3 | Tipagem estrita do frontend. Escolhido por compatibilidade declarada com `typescript-eslint <6.1`. | Projeto ativo da Microsoft. | Apache-2.0 | 7.0.2 foi rejeitado nesta data por incompatibilidade de peer range. |
| ESLint | 10.8.0 | Gate de lint semântico para TS/React. | Projeto maduro e ativo. | MIT | Apenas `tsc` não cobre hooks, imports e padrões de código. |
| `@eslint/js` | 10.0.1 | Configuração recomendada oficial de JavaScript. | Mantido junto ao ESLint. | MIT | Replicar regras manualmente aumentaria drift. |
| `typescript-eslint` | 8.65.0 | Parser e regras TypeScript com informação de tipos. | Projeto oficial do ecossistema ESLint/TS. | MIT | ESLint sem parser não entende TS; TSLint está descontinuado. |
| `eslint-plugin-react-hooks` | 7.1.1 | Regras oficiais de hooks e compiler diagnostics. | Mantido pelo projeto React. | MIT | Revisão manual não fornece gate automatizado. |
| `eslint-plugin-react-refresh` | 0.5.3 | Garante exports compatíveis com Fast Refresh no shell Vite. | Projeto ativo e usado pelo template Vite. | MIT | Omitir reduz a confiabilidade do fluxo de desenvolvimento. |
| `globals` | 17.7.0 | Conjuntos revisados de globals browser/Node para ESLint flat config. | Pacote ativo e amplamente usado. | MIT | Lista manual ficaria incompleta e desatualizada. |
| Prettier | 3.9.6 | Formatação determinística de TSX, CSS, HTML, JSON e YAML. | Projeto maduro e ativo. | MIT | ESLint stylistic não cobre todos os formatos; dprint adicionaria outro ecossistema. |
| `@types/react` | 19.2.17 | Tipos do React necessários ao modo estrito. | Mantido no DefinitelyTyped. | MIT | Tipos incompletos locais não são sustentáveis. |
| `@types/react-dom` | 19.2.3 | Tipos do renderer DOM. | Mantido no DefinitelyTyped. | MIT | Declarações locais duplicariam a API oficial. |
| `@types/node` | 24.13.3 | Tipos alinhados ao Node 24 para a configuração Vite. | Mantido no DefinitelyTyped. | MIT | Usar tipos 26 criaria APIs não disponíveis no runtime selecionado. |

## 6. Testes web

| Dependência | Versão | Finalidade e motivo | Manutenção | Licença | Alternativa considerada |
|---|---:|---|---|---|---|
| Vitest | 4.1.10 | Runner integrado ao Vite, rápido e compatível com TS. | Projeto oficial do ecossistema Vite. | MIT | Jest exigiria transformação/configuração separada. |
| Testing Library React | 16.3.2 | Teste do shell por semântica acessível, não por detalhes internos. | Projeto Testing Library ativo. | MIT | React Test Renderer está descontinuado; DOM manual é mais frágil. |
| Testing Library DOM | 10.4.1 | Peer explícito e queries semânticas usadas pelo adapter React. | Projeto Testing Library ativo. | MIT | Dependência transitiva implícita prejudicaria reprodutibilidade. |
| Testing Library jest-dom | 7.0.0 | Matchers acessíveis e legíveis para Vitest. | Projeto Testing Library ativo. | MIT | Asserções DOM manuais seriam repetitivas. |
| jsdom | 29.1.1 | DOM de teste sem navegador ou rede. | Projeto ativo e compatível com Node 24. | MIT | happy-dom foi considerado; jsdom prioriza fidelidade a padrões web. |

## 7. Package managers e ações de CI

| Dependência | Versão | Finalidade e motivo | Manutenção | Licença | Alternativa considerada |
|---|---:|---|---|---|---|
| uv | 0.11.13 | Gerencia ambiente, lock e build Python em um comando coerente. | Projeto ativo da Astral; a versão do binário está fixada na CI. | Apache-2.0 ou MIT | `pip-tools` exigiria arquivos e comandos separados para ambiente, resolução e build. |
| pnpm | 11.5.2 | Gerencia o workspace e o lock web com peers estritos e armazenamento eficiente. | Projeto ativo da pnpm; versão fixada em `packageManager`. | MIT | npm workspaces foi considerado, mas oferece menos ergonomia para filtros e validação estrita de peers. |
| `actions/checkout` | 6.0.2 | Materializa o repositório no runner para os gates. | Action oficial mantida pelo GitHub. | MIT | Checkout manual por Git aumenta configuração e risco de tratar refs incorretamente. |
| `actions/setup-python` | 6.2.0 | Instala o patch exato do Python na CI. | Action oficial mantida pelo GitHub. | MIT | Usar apenas o Python preinstalado do runner não fixa a versão. |
| `actions/setup-node` | 6.2.0 | Instala Node exato e habilita cache do pnpm. | Action oficial mantida pelo GitHub. | MIT | Runtime preinstalado e cache manual aumentariam drift e código do workflow. |
| `astral-sh/setup-uv` | 7.2.1 | Instala a versão fixada do uv e integra seu cache. | Action oficial ativa do projeto uv. | MIT | Download por script próprio aumentaria a superfície de supply chain e manutenção. |
| `pnpm/action-setup` | 6.0.8 | Instala pnpm sem executar dependências implicitamente. | Action oficial ativa do projeto pnpm e compatível com o runtime atual das Actions. | MIT | Corepack ou instalação global manual exigiriam mais passos e validação própria. |

Todas as actions estão fixadas pelo SHA do commit, e a tag revisada aparece em comentário no workflow. Atualizações exigem validar tag, commit, licença e changelog.

## 8. Persistência relacional da F2.2

Versões verificadas nos projetos oficiais e no PyPI em 28 de julho de 2026. A escolha síncrona atende migrations e testes sem antecipar concorrência de casos de uso; não define o modelo de execução futuro da API.

| Dependência | Versão | Finalidade e motivo | Manutenção | Licença | Alternativa considerada |
|---|---:|---|---|---|---|
| SQLAlchemy | 2.0.51 | Metadata e tabelas com SQLAlchemy Core; oferece tipos PostgreSQL e convenções estáveis sem acoplar o domínio a ORM. | Projeto SQLAlchemy maduro, estável e ativo. | MIT | SQL manual duplicaria tipos/constraints entre código e inspeção; ORM foi rejeitado por não haver repositório nesta tarefa. |
| Alembic | 1.18.5 | Migration versionada, transacional, com upgrade/downgrade e metadata do projeto. | Mantido pelo projeto SQLAlchemy, estável e ativo. | MIT | Scripts SQL próprios perderiam grafo de revisões e integração de metadata; Flyway adicionaria runtime/ecossistema separado. |
| Psycopg com extra `binary` | 3.3.4 | Driver PostgreSQL síncrono compatível com Python 3.14, SQLAlchemy e Alembic; o extra inclui implementação e libpq para instalação reproduzível em Windows/Linux. | Psycopg 3 é a geração atual, com PostgreSQL 10–18 e Python 3.10–3.14 suportados. | LGPL-3.0-only | `asyncpg` anteciparia async sem caso de uso; Psycopg 2 é geração anterior; build `psycopg[c]` exigiria compilador/libpq local. |

Risco específico: `psycopg-binary` incorpora bibliotecas nativas. Correções de libpq/OpenSSL chegam por atualização do pacote, não automaticamente pelo sistema operacional; o lockfile e o scanner de dependências futuro devem acompanhar seus releases. Não foi adicionado pool de conexão.

## 9. Infraestrutura de desenvolvimento

| Componente | Versão | Finalidade | Licença/manutenção | Alternativa considerada |
|---|---:|---|---|---|
| PostgreSQL oficial em container | 18.4-bookworm | Banco real e reproduzível para migration e integração local/CI. Não é dependência do produto Python. | PostgreSQL License; imagem oficial mantida no Docker Hub. | PostgreSQL instalado localmente é suportado, mas não garante ambiente limpo; SQLite é proibido por divergir em UUID, `NUMERIC`, timezone, regex e constraints. |

## 10. Dependências deliberadamente ausentes

A F2.4.1 e a F2.4.2 reutilizam exclusivamente biblioteca padrão, SQLAlchemy Core, Alembic e Psycopg já aprovados. Nenhuma dependência de autenticação, autorização, validação de e-mail ou auditoria foi adicionada.

A F3.1 implementa contratos, validação, Protocol e registro somente com a
biblioteca padrão e tipos estáveis do domínio. SemVer foi implementado na forma
mínima `MAJOR.MINOR.PATCH`; adicionar pacote externo criaria superfície de
supply chain sem resolver necessidade desta etapa. Nenhum cliente HTTP, SDK de
fonte, framework de descoberta, cache ou biblioteca de retry foi adicionado, e
os lockfiles permanecem inalterados.

A F3.2 adiciona somente simulador sintético, fixtures e validadores usando
biblioteca padrão e os tipos já aprovados. Não foram necessários framework
assíncrono de testes, biblioteca de fixtures, gerador de dados, cliente de rede,
relógio, retry ou plugin de descoberta; `uv.lock` e `pnpm-lock.yaml` permanecem
inalterados.

A F4.2 reutiliza `dataclasses`, `enum`, `hashlib`, `json`, `re`, `unicodedata`,
SQLAlchemy Core, Alembic e Psycopg já aprovados. Matching, Jaccard, normalização,
score e ranking foram implementados sem biblioteca fuzzy, transliteração,
modelo, vetor ou float. Nenhuma dependência e nenhum lockfile mudou.

A F4.3 reutiliza somente essas dependências e a biblioteca padrão para digests,
serialização canônica, materialização e coordenação transacional. Não adiciona
pacote de deduplicação, fuzzy matching, planner, fila ou cliente externo; os
lockfiles permanecem inalterados.

Não foram adicionados Redis, fila, S3, pgvector, OpenSearch, autenticação, SDK de
modelo, LangGraph, Playwright, scraper, conector real, pacote de país, scoring,
relatório, parser documental, ORM adicional ou framework de repositório.
