# ADR-0010 — Persistência relacional inicial com SQLAlchemy Core

- Status: Accepted
- Data: 2026-07-28

## Contexto

O ADR-0007 definiu PostgreSQL como fonte de verdade, mas não escolheu o modo de acesso nem as convenções do schema. A F2.2 precisa materializar `Workspace`, `Company` e `Investigation` sem acoplar o domínio a ORM, repositórios ou configuração de infraestrutura. O ADR-0008 também exige que relações preservem a fronteira de workspace por construção, e não apenas por convenção de consulta.

## Decisão

Adotar SQLAlchemy 2.x Core para metadata declarativa, Alembic para migrations manuais e Psycopg 3 em modo síncrono para PostgreSQL. Esta etapa não cria classes ORM, sessão, repositório ou Unit of Work. A URL é obrigatória em `DATABASE_URL`, sem fallback, e aceita somente o dialeto `postgresql+psycopg`.

Usar UUID nativo, `TIMESTAMP WITH TIME ZONE`, `NUMERIC` sem precisão/escala imposta e textos com `CHECK` explícito. Estados permanecem em `VARCHAR` com vocabulário limitado por constraint, em vez de enum nativo do PostgreSQL, para evitar DDL especial em futuras evoluções. Todos os nomes de primary keys, foreign keys, uniques, checks e índices seguem convenção determinística do metadata e são materializados explicitamente na migration.

Validar `official_domain` também por `CHECK`, usando a mesma forma canônica básica do domínio. A constraint protege escritas diretas contra protocolo, porta, caminho, caixa alta e labels inválidas, mas deliberadamente não afirma propriedade, atividade ou unicidade do host.

`Company` recebe unicidade técnica composta em `(id, workspace_id)`. `Investigation` referencia `(confirmed_company_id, workspace_id)` contra essa chave, além de possuir sua própria foreign key para `Workspace`. Essa redundância controlada impede que uma investigação associe uma empresa de outro tenant mesmo quando a escrita contorna o domínio. Índices de consultas de raiz começam por `workspace_id`. Row Level Security não é ativado nesta etapa.

Os testes relacionais usam PostgreSQL real e nunca SQLite. Desenvolvimento e CI usam a imagem oficial PostgreSQL 18.4 Bookworm com versão fixa; Docker Compose é apenas infraestrutura local e não integra o produto implantado.

## Decisões de invariantes da investigação

- Uma investigação em `CREATED` não possui `started_at`; o início operacional ocorre em `CREATED -> IDENTIFYING`.
- `confirmed_company_id` pode estar presente em `CREATED` quando a solicitação parte de empresa já cadastrada. Isso é uma referência inicial e não elimina validações futuras da política de identificação.
- `deadline_at`, quando presente, não pode anteceder `created_at`.
- `JurisdictionCode` e sua coluna continuam adiados até existir contrato que diferencie país, registro e jurisdição subnacional.

## Consequências

- O domínio permanece sem dependências externas e as tabelas ficam em infraestrutura.
- Migrations podem ser revistas e executadas sem importar regras de aplicação.
- O caminho síncrono reduz complexidade para DDL e testes; uma futura aplicação assíncrona poderá exigir novo adaptador, sem alterar o domínio.
- A FK composta cria um índice unique redundante em relação à PK de empresa, em troca de isolamento relacional verificável.
- Ausência de RLS significa que consultas futuras ainda deverão filtrar workspace; sua adoção exige ADR, política de conexão e testes próprios.
- O pacote binário do Psycopg facilita reprodução multiplataforma, mas incorpora bibliotecas nativas que exigem atualização coordenada pelo lockfile.
