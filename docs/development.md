# Desenvolvimento local

## 1. Escopo atual

A fundação concluída pelas tarefas F1.1 e F1.2 oferece somente:

- pacote Python vazio e independente em `src/intelligence`;
- API FastAPI com `GET /health`;
- shell React/Vite estático;
- testes, lint, formatação, tipos, builds e scanner básico de segredos.

Não há banco, fila, autenticação, modelo, conector, fonte externa ou processamento documental.

## 2. Runtimes e ferramentas

| Ferramenta | Versão de referência | Política |
|---|---:|---|
| Python | 3.14.5 | suportado em `>=3.14,<3.15` |
| uv | 0.11.13 | versão usada para gerar `uv.lock` |
| Node.js | 24.16.0 | suportado em `>=24.16.0,<25` |
| pnpm | 11.5.2 | fixado por `packageManager` |

Use as versões exatas de referência para reproduzir o ambiente da CI. `.python-version` e `.nvmrc` permitem que gerenciadores compatíveis selecionem os runtimes.

## 3. Instalação reproduzível

Na raiz do repositório:

```bash
uv sync --frozen --all-groups
pnpm install --frozen-lockfile
```

`--frozen` impede atualização silenciosa dos locks. Apenas a manutenção deliberada de dependências deve executar comandos sem essa opção e revisar o diff gerado.

Nenhuma variável de ambiente é necessária na Fase 1. O `.env.example` permanece sem valores.

## 4. Execução local

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

## 5. Comandos padronizados

| Comando | Resultado |
|---|---|
| `pnpm lint` | Ruff, ESLint e scanner básico de segredos |
| `pnpm format` | formata Python e web |
| `pnpm format:check` | verifica formatação sem escrever |
| `pnpm typecheck` | mypy estrito e TypeScript estrito |
| `pnpm test` | pytest e Vitest |
| `pnpm build` | wheel/sdist Python e bundle Vite |
| `pnpm quality` | todos os gates na ordem da CI |

Comandos específicos usam os sufixos `:python` e `:web` quando disponíveis.

## 6. Política de rede em testes

- `pytest-socket` executa o backend com sockets desabilitados por padrão.
- O teste do endpoint usa o transporte ASGI em processo e libera somente os endereços de loopback `127.0.0.1` e `::1`, necessários ao event loop no Windows; conexões a outros hosts continuam bloqueadas.
- O setup do Vitest substitui `fetch` por uma função que falha imediatamente.
- Nenhum teste depende de conta, endpoint ou serviço externo.
- Instalação de dependências pode acessar registries; isso ocorre antes dos testes.

## 7. Builds

- Python: `dist/python/` recebe wheel e source distribution.
- Web: `apps/web/dist/` recebe o bundle estático.
- Ambos são ignorados pelo Git e recriados a partir dos manifests e lockfiles.

## 8. CI

`.github/workflows/ci.yml` instala exatamente os runtimes e package managers de referência, usa os dois lockfiles em modo frozen e executa `pnpm quality`.

| Evidência | Estado em 2026-07-25 |
|---|---|
| Gates locais em ambiente limpo | Executados e aprovados; consulte `docs/validation/f1.2-clean-validation.md`. |
| Builds locais Python e web | Executados e aprovados no Windows 10. |
| Workflow de CI | Configurada e revisada localmente. |
| Execução no GitHub Actions | Não executada; o repositório não possui remoto e nenhum push foi realizado. |

Configurar a workflow não equivale a comprovar uma execução remota. Somente um run real do GitHub Actions pode alterar o último estado da tabela.

As ações de terceiros estão fixadas por SHA, com a tag revisada registrada em comentário. Atualizações exigem nova revisão do commit e do changelog correspondente.

O `uv 0.11.13` disponível no ambiente de fundação não reconheceu o download gerenciado do Python 3.14.6 para Windows. Por isso, a referência reproduzível foi fixada no Python 3.14.5 já instalado. A próxima atualização de toolchain deve atualizar primeiro o uv e então promover o patch do Python em mudança revisada.

## 9. Solução de problemas

- Se `npm.ps1` ou `pnpm.ps1` for bloqueado no PowerShell, use o executável `pnpm.cmd` ou um gerenciador de Node configurado corretamente.
- Se o runtime não corresponder, selecione as versões de `.python-version` e `.nvmrc` antes de instalar.
- Se um lock precisar mudar, explique a atualização em `docs/dependencies.md` e revise todas as dependências transitivas alteradas.
