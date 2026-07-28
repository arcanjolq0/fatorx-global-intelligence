# Plano de execução — Fator X Global Intelligence

## 1. Estado

- Fase atual: **Fase 2 — Domínio e persistência inicial**.
- Status: **F2.1 concluída em 2026-07-25; F2.2 e F2.2.1 concluídas em 2026-07-28**; aguardando nova instrução antes da F2.3.
- Código executável: API de saúde, shell web estático, ferramentas de qualidade, fundação imutável do domínio e schema PostgreSQL versionado com hardening relacional.
- Conectores reais e integrações externas: inexistentes e não autorizados.
- Dependências de aplicação: fixadas nos lockfiles e justificadas em `docs/dependencies.md`.

## 2. Objetivo de execução

Construir incrementalmente uma plataforma auditável de investigação empresarial internacional. O caminho crítico é provar primeiro os contratos de domínio, evidência, estados e conectores com simuladores; fontes reais só entram após aprovação técnica, jurídica e comercial individual.

## 3. Gates que não podem ser contornados

| Gate | Condição objetiva para avançar |
|---|---|
| G0 — Fundação | Documentos-base e ADRs revisados; riscos e perguntas comerciais registrados. |
| G1 — Ferramenta | Monorepo mínimo, tipos estritos, lint, testes e CI local funcionando sem integrações. |
| G2 — Núcleo | Modelo de domínio, migrations iniciais, invariantes e testes críticos aprovados. |
| G3 — Simulação | Contrato de conectores validado com simuladores e falhas controladas. |
| G4 — Evidência | Cadeia de custódia, claims, contradições e bloqueio de afirmações críticas testados. |
| G5 — Segurança | Threat model, SSRF, uploads, autorização, auditoria e segredos validados. |
| G6 — Fonte real | Fonte específica aprovada em termos, licença, custo, retenção, exibição e qualidade. |
| G7 — Piloto | Critérios de `docs/mvp-definition-of-done.md` atendidos e aceite humano registrado. |

## 4. Dependências e decisões pendentes

| Dependência | Bloqueia | Responsável esperado | Registro |
|---|---|---|---|
| Perfil de cliente e modelo de tenancy | autenticação, autorização, retenção | produto/comercial/segurança | `docs/open-questions.md` |
| Países e capacidades prioritárias | pacotes e seleção de fontes | comercial/produto | `docs/open-questions.md` |
| Matriz de fontes licenciadas | conectores reais e cobertura prometida | jurídico/compras/produto | `docs/source-policy.md` |
| Metodologia e apetite de risco | pesos, níveis e linguagem do relatório | crédito/compliance | `docs/scoring-methodology.md` |
| SLA, volume e orçamento por pesquisa | filas, timeouts, escala e custos | produto/operações | `docs/open-questions.md` |
| Retenção, residência e base legal | storage, expurgo e dados pessoais | jurídico/segurança | `docs/security.md` |
| Formato e aprovação do relatório | workflow de revisão e exportação | operações/produto | `docs/open-questions.md` |

Nenhuma dessas dependências autoriza suposição silenciosa. Quando ainda não validadas, o sistema deve usar configuração explícita e permanecer em modo não produtivo.

## 5. Plano incremental

### Fase 0 — Fundação documental

Entregáveis:

- regras do repositório;
- requisitos e análise crítica;
- arquitetura e estrutura proposta;
- modelo de dados;
- contratos de conectores e evidências;
- máquina de estados;
- estratégia de testes;
- segurança, fontes, países e scoring;
- critérios objetivos do MVP;
- ADRs das decisões-base.

Critério de saída: todos os artefatos listados em `docs/README.md` existem, possuem escopo explícito e não apresentam contradições materiais conhecidas.

### Fase 1 — Esqueleto técnico

**Status: concluída em 2026-07-25 pelas tarefas F1.1 e F1.2.**

Escopo:

- criar workspaces de backend e frontend e diretórios de interfaces;
- fixar versões suportadas e lockfiles;
- configurar tipos estritos, lint, formatação, testes e verificação de segredos;
- criar CI mínima;
- disponibilizar configuração local sem valores secretos;
- adicionar apenas um endpoint de saúde sem regra de negócio.

Fora de escopo: banco funcional, autenticação, filas, storage, modelo de IA e qualquer fonte externa.

Critério de saída: instalação reproduzível documentada; comandos de qualidade passam em ambiente limpo; nenhuma chamada de rede ocorre nos testes.

### Fase 2 — Domínio e persistência inicial

**Status: em andamento; F2.1 concluída em 2026-07-25; F2.2 e F2.2.1 concluídas em 2026-07-28. Repositórios e round-trip de entidades não iniciados.**

Escopo:

- implementar IDs, enums, valores monetários e timestamps tipados;
- implementar entidades centrais e invariantes de `docs/data-model.md`;
- criar schema e migrations iniciais;
- criar repositórios como portas e adaptadores PostgreSQL;
- aplicar isolamento por workspace e auditoria mínima.

Critério de saída: round-trip de persistência, constraints e migrations testados; domínio não importa infraestrutura.

#### F2.1 — Tipos fundamentais e invariantes do domínio

Status: **Concluída em 2026-07-25.**

Entregas:

- IDs fortes e imutáveis para workspace, usuário, empresa e investigação;
- códigos canônicos de país e moeda com validação de formato;
- dinheiro exato com `Decimal`, moeda explícita e operações sem conversão implícita;
- normalização obrigatória de instantes com fuso para UTC;
- snapshots imutáveis de `Workspace`, `Company` e `Investigation`;
- vocabulário completo de estados de investigação, sem implementar transições;
- erros tipados, testes unitários e teste arquitetural de independência do domínio;
- decisões, invariantes e itens adiados registrados em `docs/domain-foundation.md`.

Evidências de conclusão:

- testes cobrem caminhos válidos, formatos inválidos, tipos trocados, precisão monetária, datas inconsistentes, tenancy explícita e estado inicial;
- lint, formatação e mypy estrito aprovados;
- domínio depende somente da biblioteca padrão e não importa FastAPI, Pydantic, banco, HTTP ou outras camadas internas;
- nenhuma dependência, migration, repositório, endpoint ou integração foi adicionada.

F2.1, isoladamente, não conclui o gate G2. O schema e as constraints passaram a existir na F2.2; o round-trip por repositórios continua pendente para a F2.3.

#### F2.2 — Schema PostgreSQL e migrations iniciais

Status: **Concluída em 2026-07-28.**

Entregas:

- metadata SQLAlchemy Core e migration Alembic inicial para `Workspace`, `Company` e `Investigation`;
- PostgreSQL 18.4 real e reproduzível para desenvolvimento e CI;
- UUID nativo, timestamps com fuso, `NUMERIC` exato e constraints de vocabulário e datas;
- isolamento relacional da empresa confirmada por foreign key composta com `workspace_id`;
- configuração obrigatória e validada por `DATABASE_URL`, sem segredo ou fallback;
- testes de upgrade, upgrade repetido, downgrade, tipos, constraints, índices, isolamento e aderência do metadata;
- decisão arquitetural ADR-0010 e registro de dependências, operação e validação.

Evidências de conclusão:

- a revisão `20260728_01` executou manualmente `upgrade -> downgrade -> upgrade` em PostgreSQL 18.4;
- 99 testes Python e 1 teste web passaram; cobertura Python total de 97,34%;
- lint, formatação, tipos estritos, scanner de segredos e builds foram aprovados por `pnpm quality`;
- instalações foram verificadas com os dois lockfiles em modo frozen;
- nenhum repositório, Unit of Work, acesso da API ao banco, transição de investigação, autenticação ou integração externa foi implementado;
- detalhes, falhas intermediárias e limitações constam em `docs/validation/f2.2-postgresql-migrations.md`.

A F2.2 comprova a parcela de schema, migration e constraints do gate G2. O hardening F2.2.1 foi posteriormente autorizado sem iniciar repositórios; o round-trip de persistência e as portas/adaptadores permanecem para a F2.3.

#### F2.2.1 — Hardening relacional antes dos repositórios

Status: **Concluída em 2026-07-28.**

Entregas:

- consentimento destrutivo obrigatório e test-only para qualquer teste que execute `downgrade base`;
- allowlist de loopback, padrão estrito `fatorx_test[_sufixo]`, proibição de query string e bloqueio de variáveis libpq que possam redirecionar o alvo;
- coerência persistida entre estado, `started_at` e `completed_at`, incluindo cancelamento direto atômico;
- imagem `postgres:18.4-bookworm` fixada pelo digest confirmado da validação F2.2;
- anotações postergadas em `money.py`, sem mudança funcional ou dependência;
- testes unitários da guarda, testes PostgreSQL das constraints e validação de aderência entre metadata e migration;
- ADR-0010, ciclo de vida, segurança, desenvolvimento, estratégia de testes e registro de validação atualizados.

Evidências de conclusão:

- 36 testes unitários da guarda e 26 testes PostgreSQL passaram;
- 146 testes Python e 1 teste web passaram, com cobertura Python de 97,77%;
- lint, formatação, tipos, scanner, builds e `pnpm quality` foram aprovados;
- a revisão `20260728_01` executou novamente `upgrade -> downgrade -> upgrade` e terminou em `head`;
- a imagem executada correspondeu ao digest fixado no Compose e na CI;
- nenhum repositório, interface de persistência, Unit of Work, mapper, CRUD, endpoint ou transição foi criado;
- resultados e limitações constam em `docs/validation/f2.2.1-relational-hardening.md`.

A revisão da migration inicial foi permitida porque não há registro de promoção compartilhada ou remoto; somente bancos locais descartáveis constam das validações. O gate G2 ainda aguarda round-trip por portas e adaptadores. Não iniciar a F2.3 sem nova instrução.

### Fase 3 — Framework de conectores simulados

Escopo:

- implementar portas e envelopes de `docs/connector-contract.md`;
- registro de conectores, deadlines, idempotência, budget e taxonomia de falhas;
- criar conectores simulados determinísticos, inclusive timeout, rate limit, resposta inválida e falha parcial;
- criar suíte reutilizável de testes de contrato.

Critério de saída: qualquer conector simulado que viole o contrato falha nos testes; nenhum conector escreve no domínio ou faz acesso externo.

### Fase 4 — Orquestração e resolução de entidades

Escopo:

- implementar máquina de estados e transições atômicas;
- planejar jobs por capacidade e país;
- executar simuladores em paralelo e consolidar falhas;
- gerar candidatos e aplicar política versionada de correspondência;
- pausar e retomar em revisão humana.

Critério de saída: cenários de homônimos, confirmação, cancelamento, retomada e conclusão parcial passam de forma determinística.

### Fase 5 — Evidências, claims e revisão

Escopo:

- armazenar artefatos originais conforme política;
- implementar hash, proveniência, localização, linhagem e imutabilidade;
- implementar claims e vínculos de suporte, contradição e qualificação;
- bloquear afirmações críticas sem evidência admissível;
- registrar decisões humanas.

Critério de saída: a cadeia de evidência é reproduzível; tentativas de publicar claim crítico sem suporte são rejeitadas.

### Fase 6 — Documentos

Escopo:

- upload seguro e quarentena;
- detecção de tipo, limites e verificação de malware;
- extração em pipeline desacoplado;
- OCR somente quando necessário;
- preservação de página, tabela, moeda, unidade e texto original;
- conectores/extratores simulados para testes.

Critério de saída: documentos digitais e escaneados de fixtures geram evidências localizáveis sem executar conteúdo incorporado.

### Fase 7 — Risco preliminar e relatórios

Escopo:

- regras determinísticas e versionadas;
- trilha das entradas e regras disparadas;
- qualidade e ausência de dados separadas do risco;
- relatório rascunho com limitações e fontes;
- aprovação humana antes da exportação final.

Critério de saída: mesma entrada e versão produzem o mesmo resultado; modelo de IA não altera pontuação; relatório crítico sem revisão é bloqueado.

### Fase 8 — Interface de investigação

Escopo:

- pesquisa e confirmação de entidade;
- progresso e estados;
- evidências, contradições e revisão;
- histórico e relatório;
- acessibilidade e autorização por workspace.

Critério de saída: fluxo ponta a ponta com simuladores passa nos navegadores suportados e atende a navegação por teclado definida.

### Fase 9 — Fontes e pacotes aprovados

Escopo:

- aprovar uma fonte por vez no catálogo;
- implementar primeiro a capacidade de identidade da jurisdição comercialmente priorizada;
- medir qualidade, falso positivo, custo e latência;
- concluir um pacote antes de iniciar o próximo;
- habilitar Estados Unidos, Reino Unido e Alemanha somente quando seus gates de cobertura forem aprovados.

Critério de saída por fonte: checklist de `docs/source-policy.md` completo, testes de contrato aprovados e ativação por feature flag. O nome de uma fonte não é definido enquanto acesso e licença não forem validados.

### Fase 10 — Segurança, operação e piloto

Escopo:

- testes de carga e de falhas;
- backup, restauração e disaster recovery;
- observabilidade, alertas e runbooks;
- auditoria de permissões e dependências;
- piloto controlado e medição dos critérios do MVP.

Critério de saída: todos os itens aplicáveis de `docs/mvp-definition-of-done.md` possuem evidência de teste e aceite nominal.

### Pós-MVP

Integração com CRM, monitoramento contínuo, novos países, limites de crédito estatisticamente validados, cobrança e automações externas permanecem fora do MVP.

## 6. Tarefa de implementação concluída

**Tarefa F1.1 — Criar o esqueleto mínimo e os gates de qualidade.**

Status: **Concluída em 2026-07-25.**

Arquivos/diretórios previstos:

- configuração do workspace backend;
- `apps/api` com endpoint de saúde;
- `apps/web` com shell vazio acessível;
- `src/intelligence` apenas com limites de pacote;
- `tests` com smoke tests;
- configuração de lint, tipos, testes e CI;
- `.env.example` sem valores.

Critérios de aceitação:

1. instalação e comandos são reproduzíveis em ambiente limpo;
2. tipagem estrita, lint e testes passam;
3. não existem chamadas externas, SDKs de provedores, banco, fila ou storage ativo;
4. dependências escolhidas possuem justificativa registrada;
5. documentação de desenvolvimento é atualizada.

Evidências de conclusão:

- instalações reproduzíveis validadas com `uv sync --frozen --all-groups` e `pnpm install --frozen-lockfile`;
- lint, formatação, tipos estritos, testes, scanner de segredos e builds aprovados por `pnpm quality`;
- testes sem acesso externo, com sockets desabilitados por padrão e exceção restrita a loopback no teste ASGI;
- dependências e toolchains fixadas em `uv.lock`, `pnpm-lock.yaml` e `docs/dependencies.md`;
- CI mínima configurada em `.github/workflows/ci.yml` com ações fixadas por SHA;
- escopo revisado sem itens da Fase 2 ou posteriores.

Esta era a restrição vigente no fechamento da F1.1; as F2.1 e F2.2 foram posteriormente autorizadas e concluídas em tarefas separadas.

## 7. Fechamento F1.2

**Tarefa F1.2 — Validação limpa, Git inicial e pacote de entrega.**

Status: **Concluída em 2026-07-25.**

Evidências de conclusão:

- instalação refeita em diretório temporário sem reutilizar `.venv`, `node_modules`, builds ou caches do repositório;
- os seis manifests e lockfiles da cópia limpa tinham SHA-256 idêntico aos arquivos de origem;
- `uv sync --frozen --all-groups`, `pnpm install --frozen-lockfile` e `pnpm quality` aprovados;
- lint, formatação, tipos, testes e builds também executados e aprovados separadamente;
- 6 testes Python e 1 teste web aprovados, com cobertura Python de 93,33%;
- bloqueio de rede dos testes, scanner de segredos e regras de ignore verificados;
- primeiro commit local criado sem arquivos gerados, dependências instaladas ou artefatos ignorados;
- pacote de entrega gerado exclusivamente dos arquivos rastreados por `git archive`;
- resultados detalhados registrados em `docs/validation/f1.2-clean-validation.md`.

A workflow de CI está configurada, mas não há execução registrada no GitHub Actions. A restrição de não iniciar a Fase 2 era a vigente neste fechamento histórico; as tarefas F2.1 e F2.2 foram posteriormente autorizadas e executadas separadamente.

## 8. Protocolo de atualização do plano

- Atualize o status de uma fase apenas com evidência de seus critérios de saída.
- Registre decisão arquitetural em ADR; não edite a história de ADR aceito.
- Alterações de escopo devem atualizar requisitos, riscos, critérios do MVP e este plano.
- Uma fonte real só aparece pelo nome em configuração produtiva após o gate G6.
