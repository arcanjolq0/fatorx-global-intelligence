# Desenvolvimento local

## 1. Escopo atual

A fundação concluída pelas tarefas F1.1, F1.2, F2.1 e F2.2 oferece somente:

- pacote Python independente em `src/intelligence`, com tipos fundamentais e entidades imutáveis do domínio;
- metadata e primeira migration PostgreSQL para workspace, empresa e investigação;
- API FastAPI com `GET /health`;
- shell React/Vite estático;
- testes, lint, formatação, tipos, builds e scanner básico de segredos.

Não há repositório, sessão ORM, Unit of Work, acesso ao banco pela API, transição de investigação, fila, autenticação, modelo, conector, fonte externa ou processamento documental.

## 2. Runtimes e ferramentas

| Ferramenta | Versão de referência | Política |
|---|---:|---|
| Python | 3.14.5 | suportado em `>=3.14,<3.15` |
| uv | 0.11.13 | versão usada para gerar `uv.lock` |
| Node.js | 24.16.0 | suportado em `>=24.16.0,<25` |
| pnpm | 11.5.2 | fixado por `packageManager` |
| PostgreSQL | 18.4 | imagem `postgres:18.4-bookworm` em desenvolvimento e CI |

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

O Compose usa `postgres:18.4-bookworm`, banco `fatorx_test`, credenciais deliberadamente locais e volume nomeado `fatorx_global_intelligence_postgresql_data`. A porta local padrão é `55432` para reduzir conflito com instalações PostgreSQL existentes e pode ser alterada com `POSTGRES_PORT`.

Defina a URL apenas no processo atual. PowerShell:

```powershell
$env:DATABASE_URL="postgresql+psycopg://fatorx:test@127.0.0.1:55432/fatorx_test"
```

Bash:

```bash
export DATABASE_URL="postgresql+psycopg://fatorx:test@127.0.0.1:55432/fatorx_test"
```

As credenciais acima são públicas, fracas e exclusivas do serviço local. Não as reutilize. `pnpm db:down` encerra o container sem remover o volume. A remoção do volume apaga o banco de desenvolvimento e deve ser uma ação manual e deliberada.

### 4.2 PostgreSQL instalado localmente

Também é possível usar PostgreSQL 18.4 instalado no host. Crie explicitamente um banco descartável cujo nome contenha `test`, configure um usuário próprio e defina `DATABASE_URL` com o driver `postgresql+psycopg`. Os testes recusam host não local e banco sem `test` no nome para reduzir o risco de executar downgrade contra ambiente inadequado.

SQLite não é suportado: seus tipos, regex, constraints e semântica de migration não equivalem ao PostgreSQL adotado.

### 4.3 Migrations

Com `DATABASE_URL` definida:

```bash
pnpm db:upgrade
pnpm db:downgrade
pnpm db:upgrade
```

`alembic.ini` não contém URL. `migrations/env.py` exige a variável e usa o metadata em `src/intelligence/infrastructure/persistence/postgresql`. A revisão `20260728_01` cria somente `workspace`, `company` e `investigation`; `alembic_version` é administrada pelo Alembic.

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
| `pnpm test` | pytest e Vitest |
| `pnpm test:integration` | somente migrations/constraints no PostgreSQL real; o gate global de cobertura permanece em `pnpm test` |
| `pnpm build` | wheel/sdist Python e bundle Vite |
| `pnpm quality` | todos os gates na ordem da CI |
| `pnpm db:up` / `pnpm db:down` | inicia ou encerra o PostgreSQL local sem remover o volume |
| `pnpm db:upgrade` / `pnpm db:downgrade` | aplica `head` ou retorna a `base` |

Comandos específicos usam os sufixos `:python` e `:web` quando disponíveis.

Os testes unitários do domínio estão em `tests/unit/domain`. A política de sockets desabilitados também se aplica a eles. O teste em `tests/architecture/test_domain_boundaries.py` impede que o pacote de domínio importe frameworks, infraestrutura ou outras camadas internas.

## 7. Política de rede em testes

- `pytest-socket` executa o backend com sockets desabilitados por padrão.
- O teste do endpoint usa o transporte ASGI em processo e libera somente os endereços de loopback `127.0.0.1` e `::1`, necessários ao event loop no Windows; conexões a outros hosts continuam bloqueadas.
- O setup do Vitest substitui `fetch` por uma função que falha imediatamente.
- Nenhum teste depende de conta, endpoint ou serviço externo.
- Os testes de migration liberam somente `localhost`, `127.0.0.1` e `::1` para o PostgreSQL real; o banco precisa ter `test` no nome.
- Instalação de dependências pode acessar registries; isso ocorre antes dos testes.

## 8. Builds

- Python: `dist/python/` recebe wheel e source distribution; o sdist inclui `alembic.ini` e `migrations/`.
- Web: `apps/web/dist/` recebe o bundle estático.
- Ambos são ignorados pelo Git e recriados a partir dos manifests e lockfiles.

## 9. CI

`.github/workflows/ci.yml` instala exatamente os runtimes e package managers de referência, inicia um serviço limpo `postgres:18.4-bookworm`, usa os dois lockfiles em modo frozen e executa `pnpm quality` com `DATABASE_URL` explícita.

| Evidência | Estado |
|---|---|
| Gates locais da Fase 1 | Executados e aprovados em ambiente limpo em 2026-07-25; consulte `docs/validation/f1.2-clean-validation.md`. |
| PostgreSQL e gates locais da F2.2 | Executados e aprovados no Windows 10 em 2026-07-28; consulte `docs/validation/f2.2-postgresql-migrations.md`. |
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
- Se migrations recusarem a configuração, confirme o dialeto `postgresql+psycopg`, um host local e um banco de testes explícito. Erros não exibem a URL nem a senha.
