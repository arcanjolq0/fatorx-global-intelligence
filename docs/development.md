# Desenvolvimento local

## 1. Escopo atual

A fundação concluída pelas tarefas F1.1, F1.2, F2.1, F2.2, F2.2.1 e F2.3 oferece somente:

- pacote Python independente em `src/intelligence`, com tipos fundamentais e entidades imutáveis do domínio;
- metadata e primeira migration PostgreSQL para workspace, empresa e investigação;
- portas de aplicação para os três repositórios e Unit of Work, sem dependência de infraestrutura;
- factory explícita de engine, mapeadores puros e adaptadores SQLAlchemy Core para round-trip de `Workspace`, `Company` e `Investigation`;
- Unit of Work síncrona com uma conexão/transação compartilhada, commit explícito e rollback padrão;
- API FastAPI com `GET /health`;
- shell React/Vite estático;
- testes, lint, formatação, tipos, builds e scanner básico de segredos.

Não há sessão ORM, acesso ao banco pela API, serviço de aplicação completo, transição de investigação, fila, autenticação, membership, autorização, auditoria persistida, modelo, conector, fonte externa ou processamento documental. Isolamento no nível dos serviços, memberships e auditoria mínima pertencem à F2.4 e não estão embutidos nos repositórios.

## 2. Runtimes e ferramentas

| Ferramenta | Versão de referência | Política |
|---|---:|---|
| Python | 3.14.5 | suportado em `>=3.14,<3.15` |
| uv | 0.11.13 | versão usada para gerar `uv.lock` |
| Node.js | 24.16.0 | suportado em `>=24.16.0,<25` |
| pnpm | 11.5.2 | fixado por `packageManager` |
| PostgreSQL | 18.4 | imagem `postgres:18.4-bookworm` fixada por digest em desenvolvimento e CI |

Use as versões exatas de referência para reproduzir o ambiente da CI. `.python-version` e `.nvmrc` permitem que gerenciadores compatíveis selecionem os runtimes.

## 3. Instalação reproduzível

Na raiz do repositório:

```bash
uv sync --frozen --all-groups
pnpm install --frozen-lockfile
```

`--frozen` impede atualização silenciosa dos locks. Apenas a manutenção deliberada de dependências deve executar comandos sem essa opção e revisar o diff gerado.

`DATABASE_URL` é obrigatória somente para migrations e testes relacionais. O `.env.example` declara o nome vazio; não há fallback para banco local ou credencial embutida.

## 4. PostgreSQL local

### 4.1 Docker Compose

Suba somente a infraestrutura de desenvolvimento:

```bash
pnpm db:up
```

O Compose usa `postgres:18.4-bookworm@sha256:1961f96e6029a02c3812d7cb329a3b03a3ac2bb067058dec17b0f5596aca9296`, banco `fatorx_test`, credenciais deliberadamente locais e volume nomeado `fatorx_global_intelligence_postgresql_data`. A porta local padrão é `55432` para reduzir conflito com instalações PostgreSQL existentes e pode ser alterada com `POSTGRES_PORT`.

Defina a URL apenas no processo atual. PowerShell:

```powershell
$env:DATABASE_URL="postgresql+psycopg://fatorx:test@127.0.0.1:55432/fatorx_test"
```

Bash:

```bash
export DATABASE_URL="postgresql+psycopg://fatorx:test@127.0.0.1:55432/fatorx_test"
```

As credenciais acima são públicas, fracas e exclusivas do serviço local. Não as reutilize. `pnpm db:down` encerra o container sem remover o volume. A remoção do volume apaga o banco de desenvolvimento e deve ser uma ação manual e deliberada.

Os testes de migration executam `downgrade base` e exigem consentimento adicional definido somente no processo que executa os testes. PowerShell:

```powershell
$env:FATORX_ALLOW_DESTRUCTIVE_DATABASE_TESTS="1"
pnpm.cmd test:integration
Remove-Item Env:FATORX_ALLOW_DESTRUCTIVE_DATABASE_TESTS
```

Bash:

```bash
FATORX_ALLOW_DESTRUCTIVE_DATABASE_TESTS=1 pnpm test:integration
```

O mesmo consentimento precisa envolver `pnpm test` e `pnpm quality`, pois ambos incluem os testes PostgreSQL. Somente o valor exato `1` é aceito. A variável não é configuração de aplicação, não concede acesso e não aparece ativa em `.env.example`; ela expressa consentimento pontual para destruir o schema do banco de teste validado.

A guarda rejeita qualquer query string na URL e também `PGDATABASE`, `PGHOST`, `PGHOSTADDR`, `PGPORT`, `PGSERVICE`, `PGSERVICEFILE` ou `PGOPTIONS` quando preenchidas. Além de impedir redirecionamento de host/banco, o bloqueio de `PGOPTIONS` evita alteração indireta do `search_path` usado por migrations e downgrades.

### 4.2 PostgreSQL instalado localmente

Também é possível usar PostgreSQL 18.4 instalado no host. Crie explicitamente um banco descartável chamado `fatorx_test` ou `fatorx_test_<sufixo>`, usando apenas letras minúsculas, números e underscores no sufixo; configure um usuário próprio e defina `DATABASE_URL` com o driver `postgresql+psycopg`. Os testes aceitam somente `localhost`, `127.0.0.1` ou `::1`, exigem o nome estrito e ainda exigem consentimento explícito.

SQLite não é suportado: seus tipos, regex, constraints e semântica de migration não equivalem ao PostgreSQL adotado.

### 4.3 Migrations

Com `DATABASE_URL` definida:

```bash
pnpm db:upgrade
pnpm db:downgrade
pnpm db:upgrade
```

`alembic.ini` não contém URL. `migrations/env.py` exige a variável e usa o metadata em `src/intelligence/infrastructure/persistence/postgresql`. A revisão `20260728_01` cria somente `workspace`, `company` e `investigation`; `alembic_version` é administrada pelo Alembic.

A F2.3 não altera schema e não cria migration. A aplicação constrói o engine por `create_postgresql_engine`, que valida a mesma `DATABASE_URL`, não conecta durante import e devolve ao chamador a responsabilidade de executar `dispose()`. Repositórios só existem dentro de uma `PostgreSQLUnitOfWork` ativa.

## 5. Execução local

### API

```bash
pnpm api:dev
```

A aplicação fica disponível no endereço local informado pelo Uvicorn. Verificação:

```bash
curl http://127.0.0.1:8000/health
```

Resposta esperada:

```json
{"status":"ok","service":"fatorx-global-intelligence-api"}
```

O endpoint não consulta dependência externa.

### Web

```bash
pnpm web:dev
```

O Vite informa o endereço local. O shell não consulta a API e não possui dados fictícios.

## 6. Comandos padronizados

| Comando | Resultado |
|---|---|
| `pnpm lint` | Ruff, ESLint e scanner básico de segredos |
| `pnpm format` | formata Python e web |
| `pnpm format:check` | verifica formatação sem escrever |
| `pnpm typecheck` | mypy estrito e TypeScript estrito |
| `pnpm test` | pytest e Vitest; exige consentimento destrutivo porque inclui PostgreSQL |
| `pnpm test:integration` | migrations, constraints, repositórios, round-trip e transações no PostgreSQL real; exige a guarda destrutiva e o gate global de cobertura permanece em `pnpm test` |
| `pnpm build` | wheel/sdist Python e bundle Vite |
| `pnpm quality` | todos os gates na ordem da CI; exige o mesmo consentimento destrutivo |
| `pnpm db:up` / `pnpm db:down` | inicia ou encerra o PostgreSQL local sem remover o volume |
| `pnpm db:upgrade` / `pnpm db:downgrade` | aplica `head` ou retorna a `base` |

Comandos específicos usam os sufixos `:python` e `:web` quando disponíveis.

Os testes unitários do domínio estão em `tests/unit/domain`. A política de sockets desabilitados também se aplica a eles. O teste em `tests/architecture/test_domain_boundaries.py` impede que o pacote de domínio importe frameworks, infraestrutura ou outras camadas internas.

Mapeadores, engine e ciclo de vida da Unit of Work possuem testes sem banco em `tests/unit/infrastructure/persistence/postgresql`. Os round-trips e comportamentos transacionais reais ficam em `tests/integration/persistence/test_repositories.py`. Os testes arquiteturais também impedem que aplicação importe infraestrutura, que portas importem SQLAlchemy/Alembic, que um módulo abra conexão no import e que repositórios executem commit.

## 7. Política de rede em testes

- `pytest-socket` executa o backend com sockets desabilitados por padrão.
- O teste do endpoint usa o transporte ASGI em processo e libera somente os endereços de loopback `127.0.0.1` e `::1`, necessários ao event loop no Windows; conexões a outros hosts continuam bloqueadas.
- O setup do Vitest substitui `fetch` por uma função que falha imediatamente.
- Nenhum teste depende de conta, endpoint ou serviço externo.
- Os testes de migration e repositório liberam somente `localhost`, `127.0.0.1` e `::1` para o PostgreSQL real, aceitam somente `fatorx_test` ou `fatorx_test_<sufixo seguro>` e exigem `FATORX_ALLOW_DESTRUCTIVE_DATABASE_TESTS=1` antes de criar engine ou chamar Alembic.
- Instalação de dependências pode acessar registries; isso ocorre antes dos testes.

## 8. Builds

- Python: `dist/python/` recebe wheel e source distribution; o sdist inclui `alembic.ini` e `migrations/`.
- Web: `apps/web/dist/` recebe o bundle estático.
- Ambos são ignorados pelo Git e recriados a partir dos manifests e lockfiles.

## 9. CI

`.github/workflows/ci.yml` instala exatamente os runtimes e package managers de referência, inicia um serviço limpo com a imagem PostgreSQL fixada por digest, usa os dois lockfiles em modo frozen e executa `pnpm quality` com `DATABASE_URL` e consentimento destrutivo explícitos no job.

| Evidência | Estado |
|---|---|
| Gates locais da Fase 1 | Executados e aprovados em ambiente limpo em 2026-07-25; consulte `docs/validation/f1.2-clean-validation.md`. |
| PostgreSQL e gates locais da F2.2 | Executados e aprovados no Windows 10 em 2026-07-28; consulte `docs/validation/f2.2-postgresql-migrations.md`. |
| Hardening relacional F2.2.1 | Executado e aprovado no Windows 10 em 2026-07-28; consulte `docs/validation/f2.2.1-relational-hardening.md`. |
| Repositórios e Unit of Work F2.3 | Executados e aprovados no Windows 10 em 2026-07-28; consulte `docs/validation/f2.3-persistence-round-trip.md`. |
| Builds locais Python e web | Executados e aprovados no Windows 10 em 2026-07-28. |
| Workflow de CI | Configurada e revisada localmente. |
| Execução no GitHub Actions | Não executada; o repositório não possui remoto e nenhum push foi realizado. |

Configurar a workflow não equivale a comprovar uma execução remota. Somente um run real do GitHub Actions pode alterar o último estado da tabela.

As ações de terceiros estão fixadas por SHA, com a tag revisada registrada em comentário. Atualizações exigem nova revisão do commit e do changelog correspondente.

O `uv 0.11.13` disponível no ambiente de fundação não reconheceu o download gerenciado do Python 3.14.6 para Windows. Por isso, a referência reproduzível foi fixada no Python 3.14.5 já instalado. A próxima atualização de toolchain deve atualizar primeiro o uv e então promover o patch do Python em mudança revisada.

## 10. Solução de problemas

- Se `npm.ps1` ou `pnpm.ps1` for bloqueado no PowerShell, use o executável `pnpm.cmd` ou um gerenciador de Node configurado corretamente.
- Se o runtime não corresponder, selecione as versões de `.python-version` e `.nvmrc` antes de instalar.
- Se um lock precisar mudar, explique a atualização em `docs/dependencies.md` e revise todas as dependências transitivas alteradas.
- Se `5432` já estiver ocupada, mantenha a porta padrão `55432` do Compose ou escolha outra em `POSTGRES_PORT`; a porta da `DATABASE_URL` deve corresponder.
- Se os testes de migration recusarem a configuração, confirme o dialeto `postgresql+psycopg`, um dos três hosts locais permitidos, o padrão estrito do nome e o consentimento exato `1`. Erros não exibem a URL nem a senha.
