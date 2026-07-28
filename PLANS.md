# Plano de execução — Fator X Global Intelligence

## 1. Estado

- Fase atual: **Fase 3 — Framework de conectores simulados, limitada à F3.1**.
- Status: **F2.1 concluída em 2026-07-25; F2.2 a F2.4.2 concluídas em 2026-07-28; F3.1 implementada em 2026-07-28**. F3.2, F3.3 e fases posteriores não foram iniciadas.
- Código executável: API de saúde, shell web estático, domínio imutável, seis tabelas PostgreSQL versionadas, seis portas/adaptadores Core, Unit of Work síncrona endurecida, serviços mínimos tenant-scoped e contratos puros de conectores `1.0.0` com registro explícito. Não há autenticação, acesso pela API, simulador, executor ou I/O de conector.
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

**Status: concluída; F2.1 a F2.4.2 entregues. Nenhuma fase posterior foi iniciada.**

Escopo:

- implementar IDs, enums, valores monetários e timestamps tipados;
- implementar entidades centrais e invariantes de `docs/data-model.md`;
- criar schema e migrations iniciais;
- criar repositórios como portas e adaptadores PostgreSQL;
- aplicar isolamento estrutural por workspace nas relações e consultas;
- materializar identidades, memberships e auditoria mínima na F2.4.1, mantendo autorização e isolamento no nível dos serviços para a F2.4.2.

Critério de saída: round-trip, constraints e migrations testados; domínio não importa infraestrutura; a fundação persistida da F2.4.1 não antecipa a autorização e o isolamento de serviços da F2.4.2.

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

A revisão da migration inicial foi permitida porque não há registro de promoção compartilhada ou remoto; somente bancos locais descartáveis constam das validações. Naquele fechamento, o gate G2 ainda aguardava round-trip por portas e adaptadores; essa parcela foi posteriormente concluída pela F2.3 autorizada.

#### F2.3 — Portas de persistência, repositórios PostgreSQL e Unit of Work

Status: **Concluída em 2026-07-28.**

Entregas:

- portas pequenas e tipadas para `Workspace`, `Company`, `Investigation` e Unit of Work, sem imports de infraestrutura;
- hierarquia mínima de erros para falha, conflito, dados persistidos inválidos e uso fora de transação;
- criação pública de `Investigation` preservada em `CREATED`/versão 1 e reconstituição explícita, validada e sem transição;
- factory de engine sem conexão no import, mapeadores puros e três repositórios SQLAlchemy Core;
- consultas de empresa e investigação sempre compostas por `workspace_id` e ID, sem `SELECT *`, delete, listagem ou commit interno;
- Unit of Work síncrona, de uso único, com uma conexão/transação compartilhada, commit explícito e rollback padrão;
- bloqueio de `PGOPTIONS` na guarda destrutiva para impedir alteração de `search_path`;
- ADR-0011, testes unitários, arquiteturais e PostgreSQL reais e registro de validação.

Evidências de conclusão:

- 210 testes Python e 1 teste web passaram, com cobertura Python total de 93,70%;
- 50 testes PostgreSQL passaram, incluindo 24 cenários novos de repositórios, round-trip, isolamento e transações;
- lint, formatação, tipos estritos, scanner de segredos, builds e `pnpm quality` foram aprovados;
- `upgrade -> downgrade -> upgrade` terminou em `head`, e `alembic check` não encontrou operações novas;
- nenhuma migration, dependência, endpoint, transição, membership, autorização ou auditoria persistida foi adicionada;
- detalhes, inclusive uma falha intermediária de formatação corrigida, constam em `docs/validation/f2.3-persistence-round-trip.md`.

A F2.3 conclui a parcela de round-trip do gate G2. A Fase 2 permanece aberta para a F2.4; não iniciar essa tarefa sem nova instrução.

#### F2.3.1 — Hardening da fronteira transacional

Status: **Concluída em 2026-07-28.**

Entregas:

- guarda compartilhada que vincula os três repositórios à `Connection` e à `RootTransaction` originalmente abertas pela Unit of Work;
- validação, antes de toda leitura ou escrita, de conexão aberta, transação original ativa e identidade entre `connection.get_transaction()` e a transação original;
- rejeição de repositório capturado depois de commit, rollback, fechamento ou substituição da transação, sem permitir `autobegin` acidental;
- conexão e transação compartilhadas preservadas, com commit exclusivamente na Unit of Work;
- semântica explícita para commit e rollback duplicados e tradução de falhas de início, commit e rollback sem detalhes técnicos nas mensagens públicas;
- testes unitários e PostgreSQL reais, ADR-0011 e documentação operacional atualizados.

Evidências de conclusão:

- 225 testes Python e 1 teste web passaram, com cobertura Python total de 95,37%;
- 58 testes PostgreSQL passaram, incluindo leitura e escrita depois de commit/rollback, ausência de `autobegin`, operação normal, fechamento, finalização duplicada e falhas reais de início/commit/rollback;
- lint, formatação, tipos estritos, scanner de segredos, builds e `pnpm quality` foram aprovados;
- `upgrade -> downgrade -> upgrade` terminou em `head`, e `alembic check` não encontrou operações novas;
- nenhuma dependência, migration, funcionalidade da F2.4, endpoint ou integração foi adicionada;
- resultados, falhas intermediárias e limitações constam em `docs/validation/f2.3.1-transaction-boundary-hardening.md`.

A decisão sobre como tratar uma empresa já confirmada pertence à futura resolução de entidades/orquestração. A persistência somente mantém a referência tipada e a coerência relacional por workspace; a F2.3.1 não introduz essa política.

#### F2.3.2 — Invalidação após falhas de finalização

Status: **Concluída em 2026-07-28.**

Entregas:

- estado explícito, permanente e observável de invalidação no guard transacional;
- invalidação do guard antes de invocar commit ou rollback, tornando a Unit of Work terminal mesmo quando o SQLAlchemy lança erro e mantém a `RootTransaction` ativa;
- bloqueio de leitura, escrita e nova finalização pública depois de qualquer tentativa de commit ou rollback;
- limpeza técnica interna do `__exit__` preservada sem reabrir a fronteira pública;
- falha de entrada torna a instância não reutilizável, e falha de fechamento mantém o estado terminal;
- mensagens públicas fixas e redigidas para falhas de início, commit, rollback e fechamento;
- testes com doubles controlados e PostgreSQL real, sem alterar portas, contratos de repositório, schema ou dependências.

Evidências de conclusão:

- 226 testes Python e 1 teste web passaram, com cobertura Python total de 94,92%;
- 58 testes PostgreSQL passaram, incluindo falhas reais de início, commit e rollback e os cenários sem `autobegin` da F2.3.1;
- lint, formatação, tipos estritos, scanner de segredos, builds e `pnpm quality` foram aprovados;
- `upgrade -> downgrade -> upgrade` terminou em `head`, e `alembic check` não encontrou operações novas;
- nenhuma migration, dependência, porta, contrato de repositório ou funcionalidade da F2.4 foi adicionada;
- resultados e limitações constam em `docs/validation/f2.3.2-unit-of-work-poisoning.md`.

A invalidação é lógica e irreversível para aquela instância. Ela não substitui rollback/close técnicos: o `__exit__` ainda tenta limpar a transação e a conexão diretamente, mas nenhum método público ou repositório volta a operar.

#### F2.4.1 — Identidades internas, memberships e auditoria mínima persistida

Status: **Concluída em 2026-07-28.**

Entregas:

- `EmailAddress`, `UserAccount`, `WorkspaceMembership` e `AuditEvent` imutáveis, com IDs fortes e vocabulários fechados;
- revision `20260728_02` para `user_account`, `workspace_membership` e `audit_event`, sem alterar a migration inicial;
- e-mail canônico e único, uma membership permanente por `(workspace_id, user_id)` e eventos append-only sem payload genérico;
- `investigation.requested_by` preservado sem foreign key até haver reconciliação segura dos UUIDs existentes;
- três portas/adaptadores adicionais e os seis repositórios sob a mesma conexão, transação original e guard terminal;
- testes unitários, arquiteturais, de migration e round-trip em PostgreSQL real, documentados em `docs/validation/f2.4.1-identities-memberships-audit.md`.

Evidências de conclusão:

- 373 testes Python e 1 teste web passaram, com cobertura Python total de 94,92%;
- 101 testes PostgreSQL reais passaram;
- lint, formatação, tipos estritos, scanner, builds e `pnpm quality` foram aprovados;
- `upgrade head -> downgrade -1 -> upgrade head -> downgrade base -> upgrade head` terminou em `head`, e `alembic check` não encontrou divergências.

Limites: identidade interna não é autenticação; papel persistido não aplica permissão; não há update/delete, serviços, endpoints, contexto do ator ou auditoria automática.

#### F2.4.2 — Contexto do ator, autorização e isolamento nos serviços

Status: **Concluída em 2026-07-28.**

Entregas:

- `ActorContext` imutável, catálogo fechado de oito permissões e matriz pura para `OWNER`, `ADMIN`, `ANALYST` e `VIEWER`;
- autorizador contextual que valida usuário e membership ativos na mesma Unit of Work do caso de uso;
- serviços mínimos de Membership, Company e Investigation sem aceitar um segundo `workspace_id`;
- mudanças imutáveis de papel/estado e proteção do último owner com `SELECT ... FOR UPDATE`, filtro tenant-first e ordem determinística;
- `Investigation.requested_by` definido exclusivamente como o ator autorizado em novas criações;
- auditoria coordenada: sucesso na mesma transação da mutação, negações persistidas antes do erro seguro e falhas conhecidas sem falso sucesso;
- testes unitários, arquiteturais e PostgreSQL reais, inclusive corridas concorrentes, documentados em `docs/validation/f2.4.2-service-authorization-isolation.md`.

Evidências de conclusão:

- 494 testes Python e 1 teste web passaram, com cobertura Python total de 95,54%;
- 113 testes PostgreSQL reais passaram;
- as corridas concorrentes de desativação e rebaixamento foram repetidas três vezes no gate dedicado;
- instalações frozen, lint, formatação, tipos estritos, scanner, builds, `pnpm quality` e ciclo Alembic completo foram aprovados;
- `alembic check` não detectou operação nova, confirmando ausência de migration na F2.4.2.

Limites: `ActorContext` não autentica nem representa sessão/token; o bootstrap do primeiro owner permanece adiado; leituras bem-sucedidas não são auditadas nesta etapa; ator inexistente não pode produzir evento persistido devido à FK obrigatória de auditoria. Não foram criados endpoints, middleware, JWT/OAuth, migrations, dependências, transições de investigação, conectores ou integrações externas.

### Fase 3 — Framework de conectores simulados

**Status: em andamento; somente F3.1 concluída. O gate G3 permanece aberto para F3.2 e F3.3.**

Escopo:

- implementar portas e envelopes de `docs/connector-contract.md`;
- registro de conectores, deadlines, idempotência, budget e taxonomia de falhas;
- criar conectores simulados determinísticos, inclusive timeout, rate limit, resposta inválida e falha parcial;
- criar suíte reutilizável de testes de contrato.

Critério de saída: qualquer conector simulado que viole o contrato falha nos testes; nenhum conector escreve no domínio ou faz acesso externo.

#### F3.1 — Contratos tipados e registro de conectores

Status: **Concluída em 2026-07-28.**

Entregas:

- pacote `intelligence.connectors` somente com biblioteca padrão e tipos estáveis do domínio;
- IDs fortes de integração, SemVer mínimo e contrato inicial `1.0.0`;
- descritor imutável com cobertura `GLOBAL` ou `COUNTRY_SET` explícita;
- vocabulários fechados de capacidade, operação, acesso, modo, status, falha, retenção e warnings;
- contexto, query, candidato opaco, observações neutras, artefatos, metadados e outcomes imutáveis;
- `Connector` Protocol assíncrono e `ConnectorRegistry` explícito, determinístico e sem descoberta dinâmica;
- ADR-0014, testes unitários/arquiteturais e registro de validação.

Evidências de conclusão:

- 678 testes Python e 1 teste web passaram, com cobertura Python total de 95,03%;
- 200 testes focados/arquiteturais comprovaram 94,21% de branch coverage em `intelligence.connectors`;
- 113 testes PostgreSQL reais passaram sem alteração de schema;
- instalações frozen, lint, formatação, tipos estritos, scanner, builds e `pnpm quality` foram aprovados;
- `alembic check` não detectou operação nova e a revisão permaneceu `20260728_02 (head)`.

Limites: não há simulador, suíte comum de conectores, runner, retry, deadline
efetivo, cancelamento efetivo, idempotência, cache, HTTP, rede, persistência,
job, transição, orquestração, resolução, evidência, claim, scoring ou relatório.
F3.2 e F3.3 exigem autorização e tarefas próprias; a conclusão da F3.1 não
fecha o gate G3.

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
