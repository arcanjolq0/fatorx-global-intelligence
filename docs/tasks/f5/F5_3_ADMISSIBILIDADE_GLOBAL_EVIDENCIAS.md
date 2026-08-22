# F5.3 — Decisões globais de admissibilidade de Evidence

## Status

**DRAFT ARQUITETURAL — IMPLEMENTAÇÃO NÃO INICIADA.**

Esta task documenta a unidade futura aprovada para desenho arquitetural. Não
autoriza código, testes, migration, banco, dependência, commit, tag, F5.4,
lifecycle, fonte real ou fechamento do Gate G4. O ADR 0026 permanece
`Proposed` até implementação e revisão independente futuras.

## Baseline obrigatório

Antes de qualquer implementação futura, confirmar:

- branch `main` ou outra explicitamente autorizada;
- HEAD mínimo `086f35d27053f0edc0a6c75a372ea9115fbfdae2` ou sucessor aprovado;
- `origin/main` reconciliado com a baseline autorizada;
- tags `f5.1-final`, `f5.2-review-candidate` e `f5.2-final` preservadas;
- F5.1 e F5.2 `CLOSED — APPROVED_WITH_FIXES`;
- ADRs 0024 e 0025 `Accepted`;
- ADR 0026 `Proposed` até o gate independente;
- migration head `20260821_12` ou sucessor explicitamente reconciliado;
- working tree limpa ou alterações existentes identificadas e preservadas.

Se branch, HEAD, migrations, escopo ou autorização divergirem, parar e reportar
antes de alterar arquivos.

## Objetivo

Materializar futuramente a menor fronteira capaz de decidir se uma versão exata
de Evidence é admissível para `INTERNAL_FACTUAL_EVIDENCE_USE`, sob política
versionada, corpus sintético controlado, decisão humana rastreável e projeção
efetiva reproduzível, sem alterar Evidence F5.1 nem antecipar revisão de Claim.

## Escopo

### Incluído

- `EvidenceAdmissibilityDecision` imutável e append-only;
- `EvidenceAdmissibilityHistory` fail-closed;
- requested actions `ADMIT`, `RESTRICT` e `REJECT`;
- outcomes persistidos `ADMISSIBLE`, `RESTRICTED` e `REJECTED`;
- purpose `INTERNAL_FACTUAL_EVIDENCE_USE`;
- admission basis `CONTROLLED_TEST_EVIDENCE`;
- política `F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1`;
- trust root sintético próprio e versionado;
- projeção `EffectiveEvidenceAdmissibility` com `as_of` explícito;
- expiração derivada e revogação dominante;
- comando, resultado e serviço internos;
- autorização, self-approval, auditoria e idempotência;
- porta pequena e integração futura com a Unit of Work;
- uma tabela PostgreSQL e uma migration futura;
- testes de domínio, aplicação, persistência, concorrência e segurança;
- regressões integrais F5.1 e F5.2;
- documentação, validação e revisão independente próprias.

### Fora de escopo

- update de `Evidence.admissibility_status`;
- tabela ou cache de status efetivo;
- alteração de Artifact, Evidence, EvidenceLifecycleEvent, Claim ou links F5.2;
- `ClaimReviewDecision`, revisão/aprovação/factualidade de Claim;
- gate de Claim crítica ou conflito factual;
- papel `REVIEWER` ou workflow `PROPOSE`;
- transições `COLLECTING -> NORMALIZING -> VERIFYING`;
- fonte/conector real, catálogo ou aprovação G6;
- relatório, exportação, redistribuição ou publicação;
- risco, scoring, crédito, modelo ou IA;
- HTTP, API, frontend, jobs, workers, filas, scheduler ou outbox;
- F5.4 ou fechamento do Gate G4.

## Componentes e arquivos previstos

Os nomes finais deverão seguir a organização vigente e permanecer limitados ao
necessário.

### Domínio

- módulo especializado em `intelligence.evidence` para decisão, história,
  projeção e erros;
- identificadores fortes estritamente necessários em
  `intelligence.domain.identifiers`;
- nenhuma dependência de aplicação, persistência, orchestration ou framework.

### Aplicação

- contratos de comando/resultado de admissibilidade;
- trust root e política cross-aggregate em módulo próprio da aplicação;
- serviço interno dedicado;
- extensão pequena de permissões, audit actions/reasons, portas e Unit of Work;
- erros públicos constantes e redigidos.

### Persistência

- metadata própria para `evidence_admissibility_decision`;
- mapper que reconstitua domínio e recalcule digests;
- adapter PostgreSQL especializado;
- composição explícita na PostgreSQL Unit of Work;
- migration única posterior a `20260821_12`.

### Testes

- unitários de domínio, projeção, comandos, política, autorização e auditoria;
- integração PostgreSQL, migration, tenancy, tamper e rollback;
- concorrência real controlada;
- arquitetura e segurança;
- regressões F5.1/F5.2.

## Domínio

### Vocabulários fechados

Planejar tipos equivalentes a:

- `EvidenceAdmissibilityPurpose.INTERNAL_FACTUAL_EVIDENCE_USE`;
- `EvidenceAdmissionBasis.CONTROLLED_TEST_EVIDENCE`;
- `EvidenceAdmissibilityRequestedAction.ADMIT`;
- `EvidenceAdmissibilityRequestedAction.RESTRICT`;
- `EvidenceAdmissibilityRequestedAction.REJECT`.

Outcomes persistidos reutilizam a semântica global já documentada:

- `ADMISSIBLE`;
- `RESTRICTED`;
- `REJECTED`.

`PENDING`, `EXPIRED` e `REVOKED` são produzidos pela projeção, não por requested
action.

Reason codes devem ser fechados, limitados e compatíveis com a ação. A
implementação deverá distinguir claramente:

- revisão positiva de Evidence sintética controlada;
- limitação de política, uso, temporalidade ou verificabilidade;
- rejeição por conteúdo, locator, entidade ou temporalidade inadequados;
- erros de integridade, tenancy e versão, que falham em vez de virar outcome.

Não aceitar reason livre nem converter `ADMIT` negado em `RESTRICTED`.

### EvidenceAdmissibilityDecision

Campos mínimos:

- `id`;
- `workspace_id`;
- `investigation_id`;
- `subject_company_id`;
- `entity_resolution_decision_id`;
- `evidence_id`;
- `evidence_series_id`;
- `evidence_version`;
- `evidence_digest`;
- `decision_sequence`;
- `supersedes_decision_id`;
- `outcome`;
- `reason_code`;
- `policy_id`;
- `policy_version`;
- `purpose`;
- `admission_basis`;
- `controlled_trust_root_id`, version e digest obrigatórios na policy V1;
- `valid_until` somente quando permitido;
- `command_id`;
- `command_digest`;
- `decided_by`;
- `decided_at`;
- `schema_version`;
- `decision_digest`.

Excluir de domínio, persistência, `repr`, erros e audit:

- conteúdo bruto;
- locator integral;
- ClaimValue;
- justificativa livre;
- source metadata textual usada como confiança;
- payload arbitrário.

### EvidenceAdmissibilityHistory

Invariantes:

1. primeira decisão tem sequência 1 e predecessor ausente;
2. próximas decisões têm sequência contígua;
3. predecessor é exatamente a decisão anterior da mesma versão de Evidence;
4. escopo, Evidence ID/version/digest, purpose e admission basis permanecem
   coerentes na história;
5. `ADMISSIBLE` pode ter `valid_until` futuro ou ausente;
6. `RESTRICTED` e `REJECTED` exigem `valid_until = None`;
7. toda decisão V1 preserva policy ID/version, purpose, admission basis e o
   mesmo formato obrigatório de trust-root ID/version/digest;
8. `decided_at >= Evidence.created_at`;
9. `decided_at` é estritamente anterior ao `occurred_at` de supersessão ou
   revogação aplicável;
10. digests e schemas são recalculados na reconstituição;
11. ausência, linha extra, bifurcação, predecessor errado, troca de escopo ou
    decisão fora do intervalo histórico falham fechado.

Não existe retorno para `PENDING` por comando. Reversão é decisão superseding.

### Correção e revogação

Correção F5.1 cria outra versão de Evidence. A nova versão começa efetivamente
`PENDING`, e decisões anteriores não são herdadas. Uma versão superseded não
aceita decisão nova.

Revogação continua sendo evento terminal F5.1. `REVOKED` não é outcome da
decisão, prevalece no status efetivo e bloqueia decisões posteriores. História
anterior permanece reproduzível por `as_of` anterior ao evento.

Supersessão e revogação produzem efeitos somente em cortes com
`as_of >= event.occurred_at`. Não tornam retroativamente inválida uma decisão
que pertencia ao intervalo histórico anterior. A operação normal valida o
intervalo sob lock; mapper, história e projeção repetem a validação contra
persistência adulterada.

## Trust root V1

Criar futuramente manifesto interno imutável com namespace próprio, por exemplo:

`F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1`

Sua unidade deverá vincular exatamente:

- `artifact_original_sha256`;
- `evidence_content_sha256`;
- `evidence_kind`;
- `locator_type`;
- `locator_digest` calculado por `locator_to_canonical_json` F5.1.

Requisitos:

- manifest ID/version/digest próprios;
- serialização e ordenação canônicas;
- hashes normalizados e estritos;
- duplicatas normalizadas invalidam todo o manifesto;
- toda âncora deriva de fixture sintética rastreada e recomputável;
- nenhum magic hash;
- nenhuma leitura de SQL, filesystem runtime ou environment para confiar em
  entrada arbitrária;
- comando não fornece manifesto, âncora ou digest;
- source ID, origin type, filename, método, prefixo e label nunca substituem a
  âncora exata.

Toda decisão V1 registra `controlled_trust_root_id`, version e digest, além de
policy ID/version, purpose e admission basis. Isso vale para `ADMISSIBLE`,
`RESTRICTED` e `REJECTED`. Em decisão negativa, o snapshot identifica apenas a
raiz consultada pela policy; não afirma match positivo da Evidence.

O manifesto F5.2 não é suficiente, ainda que a combinação também seja
`ELIGIBLE`. Nenhuma fonte real pode produzir `ADMISSIBLE` na V1. Não criar
aprovação G6 fictícia.

## Política V1

Identificador:

`F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1`

Finalidade:

`INTERNAL_FACTUAL_EVIDENCE_USE`

Base:

`CONTROLLED_TEST_EVIDENCE`

### Preconditions para ADMIT

1. história da Evidence íntegra;
2. target é versão corrente;
3. ID, version e digest correspondem ao esperado;
4. mesmo workspace, Investigation, Company e decisão de entidade;
5. não superseded nem revoked;
6. Artifact íntegro e no mesmo escopo;
7. match único e exato no trust root F5.3;
8. `EXCERPT_ONLY`, `INDEFINITE` e `FULL` na V1;
9. `content_original` presente e coerente com `content_sha256`;
10. timestamps e demais invariantes temporais F5.1 íntegros;
11. `decided_at >= Evidence.created_at`;
12. `decided_at < event.occurred_at` para supersessão/revogação aplicável;
13. `requested_valid_until > decided_at`, quando fornecido;
14. policy, purpose, basis e trust-root snapshot canônicos;
15. `decided_by != Evidence.created_by` da versão alvo;
16. ausência de precondição material desconhecida.

A V1 não possui threshold genérico de freshness, atualidade comercial ou
validade por categoria. Não existe prazo automático. `ADMISSIBLE` sem
`valid_until` é válido; freshness de fonte/categoria exige policy posterior.

Falha de qualquer requisito bloqueia `ADMIT`. Falha de integridade é erro, não
decisão restritiva. A policy não consulta rede, catálogo real, segredo, relógio
global ou conteúdo externo executável.

### Negative decisions

`RESTRICT` e `REJECT` podem ser solicitados pelo autor da Evidence, pois
reduzem confiança e são fail-safe. A versão ainda deve ser corrente, íntegra,
tenant-scoped e não revogada. Ação e reason precisam ser semanticamente
compatíveis.

Mesmo sem match positivo no manifesto, decisões negativas preservam o snapshot
obrigatório da raiz consultada para reprodução da policy.

Uma mudança posterior para `ADMISSIBLE` exige nova decisão e reaplica todas as
preconditions, inclusive self-approval.

## Comandos e resultados

### DecideEvidenceAdmissibility

O comando futuro deverá aceitar somente:

- command ID;
- Investigation ID;
- Evidence ID e digest esperado;
- expected previous decision digest, ausente na primeira decisão;
- requested action;
- reason code fechado;
- `requested_valid_until` opcional somente para `ADMIT`.

Workspace e ator vêm do `ActorContext`. Policy, purpose, basis, manifest,
outcome, `decided_at`, decision digest e status efetivo são produzidos pelo
sistema.

O command digest usa representação canônica e não inclui conteúdo bruto. O
`repr` é redigido.

`requested_valid_until` não é copiado cegamente: a policy o aceita somente
quando for estritamente posterior ao `decided_at`. Valor igual ou anterior é
rejeitado. A ausência não produz validade automática.

### Caso de uso

1. valida tipos e forma do comando;
2. autoriza o ator antes de lookup de recurso;
3. adquire command lock;
4. resolve replay/collision;
5. exige Investigation em `VERIFYING`;
6. bloqueia e relê `EvidenceHistory`;
7. bloqueia e relê a história de admissibilidade;
8. valida expected Evidence/decision digests;
9. reconstitui e valida Artifact;
10. executa policy e self-approval;
11. constrói decisão e história completas;
12. chama o adapter somente após validação;
13. adiciona auditoria de sucesso;
14. faz commit único.

Na execução original bem-sucedida,
`operation_as_of = decision.decided_at`. Replay íntegro não lê Clock, gera ID,
escreve auditoria ou recalcula o status no tempo corrente. Ele reutiliza a
decisão e seu `decided_at` persistidos. Collision e estado stale falham fechado.

### Resultados

O resultado de mutação retorna:

- história da decisão;
- `EffectiveEvidenceAdmissibility` calculada em
  `operation_as_of = decision.decided_at`;
- `replayed`.

Exemplo obrigatório: uma decisão `ADMISSIBLE` criada em T1 com
`valid_until = T2` retorna a projeção da operação em T1 mesmo quando o mesmo
comando é repetido depois de T2. Para obter o status em T3, o consumidor usa a
leitura separada de história/status com `as_of = T3`, que retorna `EXPIRED`.

Não retornar conteúdo, locator, origem, ClaimValue nem classificação de Claim.

## Effective projection

`EffectiveEvidenceAdmissibility` será derivada e não persistida.

Para a série e o instante `as_of`:

1. reconstituir a história F5.1 e a história de decisões;
2. se `as_of < first_evidence.created_at`, produzir ausência/erro tipado de
   recurso inexistente no corte; nunca `PENDING`;
3. aplicar somente eventos com `event.occurred_at <= as_of`;
4. se houver revogação aplicável, retornar `REVOKED`;
5. selecionar a versão corrente no corte;
6. validar que toda decisão dessa versão pertence ao intervalo entre sua criação
   e eventual supersessão/revogação; adulteração falha fechado;
7. selecionar a última decisão válida dessa versão com `decided_at <= as_of`;
8. sem decisão, retornar `PENDING`;
9. decisão `RESTRICTED`, retornar `RESTRICTED`;
10. decisão `REJECTED`, retornar `REJECTED`;
11. decisão `ADMISSIBLE` com `valid_until` e `as_of >= valid_until`, retornar
    `EXPIRED`;
12. caso contrário, retornar `ADMISSIBLE`.

Não usar `datetime.now()` no domínio. Mesma história e mesmo `as_of` devem
produzir resultado idêntico.

Leitura anterior à supersessão/revogação continua reproduzindo a versão e a
decisão então vigentes. No corte igual ou posterior ao evento, a supersessão
seleciona a nova versão — inicialmente `PENDING` — e a revogação retorna
`REVOKED`. Nenhum efeito é retroativo.

## Lifecycle

Mutação é permitida somente com Investigation já em `VERIFYING`. Não adicionar
transição para chegar a esse estado.

Leitura histórica poderá aceitar `VERIFYING`, `ANALYZING`,
`WAITING_FOR_REVIEW`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED` e
`CANCELLED`, com lista fechada e testes exaustivos.

O runtime continuará sem caminho normal de `COLLECTING` até `VERIFYING`. Testes
podem reconstituir snapshots válidos; não podem decidir em `COLLECTING`.

## Autorização

Permissões fechadas futuras equivalentes a:

- `EVIDENCE_ADMISSIBILITY_READ`;
- `EVIDENCE_ADMISSIBILITY_ADMIT`;
- `EVIDENCE_ADMISSIBILITY_RESTRICT`;
- `EVIDENCE_ADMISSIBILITY_REJECT`;
- `EVIDENCE_ADMISSIBILITY_SUPERSEDE`.

| Papel   | Read | Admit | Restrict | Reject | Supersede |
| ------- | ---: | ----: | -------: | -----: | --------: |
| OWNER   |  sim |   sim |      sim |    sim |       sim |
| ADMIN   |  sim |   sim |      sim |    sim |       sim |
| ANALYST |  sim |   não |      não |    não |       não |
| VIEWER  |  sim |   não |      não |    não |       não |

`ADMIT` ainda exige ator distinto de `created_by` da versão exata. Não existe
`REVIEWER` nem `PROPOSE`.

## Auditoria

Ações fechadas mínimas:

- decisão inicial de admissibilidade;
- decisão superseding;
- leitura negada, se aplicável ao padrão vigente.

Reasons mínimos devem distinguir:

- autorização negada;
- self-approval;
- contexto/lifecycle inválido;
- Evidence ausente, superseded, revoked ou stale;
- policy/trust root não satisfeitos;
- predecessor inválido;
- command collision;
- história persistida inválida.

Usar `INVESTIGATION` como resource type. Sucesso compartilha commit com a
decisão; negação/falha conhecida segue o padrão standalone.

Não registrar conteúdo, locator, hashes, source metadata, razão livre, manifest
digest ou ID cross-tenant.

## Porta e Unit of Work

`EvidenceAdmissibilityDecisionRepository` terá somente:

- `acquire_command_lock`;
- `acquire_history_lock`;
- `add_initial`;
- `add_superseding`;
- `get_history`;
- `get_history_by_command`.

Proibir `update`, `delete`, `save`, `replace`, commit, rollback ou conexão
própria. A Unit of Work expõe a porta e coordena Evidence, Artifact, decisão e
audit na mesma transação.

## Concorrência

### Ordem obrigatória

1. command lock;
2. Evidence history lock;
3. admissibility decision history lock;
4. releitura integral;
5. validação;
6. policy;
7. construção;
8. append;
9. audit;
10. commit.

### Corridas obrigatórias

- decisão contra correção de Evidence;
- decisão contra revogação de Evidence;
- duas decisões iniciais;
- duas decisões superseding;
- decisão com predecessor/digest stale;
- mesmo command ID e digest;
- mesmo command ID com digest divergente;
- ordens de entrada diferentes sem deadlock.

Resultados válidos: replay idêntico ou exatamente uma decisão aplicável. A
operação posterior relê e falha por stale/superseded/revoked quando necessário.

Replay sempre usa `operation_as_of = persisted_decision.decided_at`; não adquire
Clock para refletir expiração que ocorreu depois da operação original.

## Persistência PostgreSQL

### Tabela evidence_admissibility_decision

Planejar somente uma tabela com:

- PK `id`;
- colunas de workspace, Investigation, Company e decisão de entidade;
- Evidence ID, series ID, version e digest;
- decision sequence e predecessor;
- outcome/reason;
- policy ID/version, purpose e admission basis;
- trust root ID/version/digest obrigatórios para todos os outcomes V1;
- `valid_until`;
- command ID/digest;
- ator/instante;
- schema version e decision digest.

Candidate keys e constraints mínimas:

- UNIQUE tenant-scoped de command ID;
- UNIQUE tenant-scoped de `(evidence_id, decision_sequence)`;
- chave candidata composta necessária para predecessor tenant-scoped;
- primeira decisão sem predecessor;
- decisão posterior com predecessor obrigatório e sequência contígua;
- predecessor da mesma Evidence exata;
- FK composta para a mesma linha real de Evidence incluindo obrigatoriamente
  `evidence_id`, `evidence_series_id`, `evidence_version`, `workspace_id`,
  `investigation_id`, `subject_company_id` e
  `entity_resolution_decision_id`;
- FK para ator e referências de escopo vigentes;
- checks de enum, outcome/reason, policy, purpose, basis, schema e digest;
- `valid_until` permitido somente para `ADMISSIBLE` e posterior a `decided_at`;
- `ADMISSIBLE`/`RESTRICTED`/`REJECTED` com trust-root snapshot completo e não
  nulo na policy V1;
- `RESTRICT` em deleção, sem cascade destrutiva.

Índices tenant-first:

- `(workspace_id, command_id)`;
- `(workspace_id, evidence_id, decision_sequence DESC)`;
- `(workspace_id, investigation_id, decided_at)`;
- predecessor e FKs que não estejam cobertos pelas chaves anteriores.

Não criar tabela de status efetivo, trigger de relógio, update ou delete.

## Migration futura

- revision posterior a `20260821_12`, somente após autorização explícita;
- não editar migrations F5.1/F5.2;
- inspecionar as candidate keys existentes da tabela `evidence`;
- reutilizar uma chave existente somente se ela vincular ID, series, version,
  workspace, Investigation, subject Company e decisão de entidade à mesma linha;
- caso contrário, adicionar somente a candidate key composta estritamente
  necessária para a FK tenant-first completa;
- criar somente `evidence_admissibility_decision` e essa chave candidata quando
  realmente necessária;
- preservar integralmente os dados atuais;
- usar nomes estáveis para constraints e índices;
- downgrade deve recusar perda quando houver decisões;
- testar banco vazio, upgrade a partir do head anterior, metadata convergence,
  downgrade protegido, re-upgrade e preservação F5.1/F5.2.

## Segurança

Controles obrigatórios:

- self-approval positivo bloqueado;
- outcome não vem pronto do ator;
- autorização antes de resource lookup;
- queries e locks tenant-first;
- Evidence/digest/predecessor esperados;
- FK e mapper vinculando Evidence ID/series/version/contexto à mesma linha;
- revogação dominante;
- trust root interno imutável e não controlável em runtime;
- manifesto F5.2 nunca suficiente;
- source metadata textual nunca suficiente;
- nenhuma fonte real admissível na V1;
- história append-only e downgrade protegido;
- replay/collision tenant-scoped;
- `ActorContext` como única origem de ator/workspace;
- reconstituição e digest fail-closed;
- intervalo histórico de cada decisão validado sob lock e na reconstituição;
- replay com cutoff persistido, sem Clock atual;
- trust-root snapshot obrigatório também em decisões negativas, sem significar
  match positivo;
- redaction em comando, resultado, erro, `repr`, log e audit;
- ausência de rede, filesystem runtime, segredo, parser ou código externo.

Threats a testar explicitamente: self-approval, forged reviewer,
actor-controlled outcome, IDOR/cross-tenant, stale approval, approval after
revocation, approval laundering entre versões, source trust bypass, manifesto
F5.2 tratado como G6, series/version desacoplados, decisão fora do intervalo
histórico, tamper de policy/purpose/trust digest, destructive history mutation e
replay/collision.

## Testes obrigatórios

### Domínio e projeção

- `as_of` anterior à criação da Evidence produz ausência tipada, nunca `PENDING`;
- série existente sem decisão → `PENDING`;
- `ADMIT` válido → `ADMISSIBLE`;
- `ADMISSIBLE` sem `valid_until` é permitido;
- `requested_valid_until <= decided_at` é rejeitado;
- `RESTRICT` → `RESTRICTED`;
- `REJECT` → `REJECTED`;
- decisões superseding em todas as reversões permitidas;
- sequência não contígua e predecessor errado;
- versão antiga não recebe decisão;
- correção cria versão nova `PENDING`;
- revogação domina qualquer decisão;
- Evidence revogada não recebe decisão;
- `ADMISSIBLE` expira exatamente quando `as_of >= valid_until`;
- antes de `valid_until` continua `ADMISSIBLE`;
- `RESTRICTED` e `REJECTED` não expiram;
- `PENDING` não expira;
- `as_of` anterior a decisão/revogação reproduz história anterior;
- decisão com `decided_at < Evidence.created_at` falha;
- decisão adulterada em/após supersession falha;
- decisão adulterada em/após revocation falha;
- leitura anterior à supersession continua reproduzível;
- leitura anterior à revocation continua reproduzível;
- supersession e revocation não são retroativas;
- mesma entrada e `as_of` produzem mesmo resultado;
- nenhum relógio escondido no domínio;
- tamper de digest, schema, policy, purpose, basis e trust root.

### Política e trust root

- match sintético completo permite continuar o `ADMIT`;
- Artifact conhecido isoladamente não admite;
- conteúdo, kind, locator type ou locator digest divergentes não admitem;
- manifesto F5.2 sozinho não admite;
- `ELIGIBLE` F5.2 não implica `ADMISSIBLE`;
- source ID, origin type, filename, acquisition method, prefixo e label não
  admitem;
- fonte real não admite na V1;
- duplicata normalizada invalida manifesto;
- cada âncora e manifest digest são recomputáveis de fixture rastreada;
- magic hash é bloqueado;
- storage diferente de `EXCERPT_ONLY` bloqueia `ADMIT`;
- retention diferente de `INDEFINITE` bloqueia `ADMIT`;
- display diferente de `FULL` bloqueia `ADMIT`;
- conteúdo ausente ou hash divergente bloqueia/falha conforme integridade;
- finalidade ou policy version diferente falha fechado;
- nenhum threshold oculto de freshness/atualidade/categoria;
- decisões negativas preservam policy/purpose/basis e trust-root snapshot;
- trust-root snapshot em `RESTRICTED`/`REJECTED` não implica match positivo;
- `ADMIT` negado não vira `RESTRICTED` automaticamente.

### Aplicação e autorização

- matriz exaustiva dos quatro papéis e novas permissões;
- self-approval `ADMIT` por criador da versão é bloqueado;
- self `RESTRICT` e self `REJECT` são permitidos;
- correção por outro ator altera somente `created_by` da nova versão usada na
  comparação;
- comando não aceita outcome/policy/purpose/manifest/decided_at prontos;
- mutação somente em `VERIFYING`;
- `COLLECTING` rejeitado;
- leitura nos estados posteriores e terminais permitidos;
- validação completa antes do primeiro append;
- erros e resultados redigidos.

### Replay, tenancy e concorrência

- replay idêntico sem novo ID, clock ou audit;
- replay após expiration mantém `operation_as_of` e resultado original;
- leitura posterior com novo `as_of` retorna `EXPIRED`;
- collision sob mesmo command ID;
- command ID igual em workspaces diferentes permanece isolado;
- lookup e predecessor cross-tenant aparecem como ausentes;
- decisão×correção, decisão×revogação e decisão×decisão;
- stale Evidence digest e stale previous decision digest;
- exatamente uma mutação válida, sem bifurcação;
- locks instrumentados sem sleep arbitrário.

### Auditoria

- sucesso no mesmo commit;
- denied/failure no padrão standalone;
- rollback não deixa decisão/audit parcial;
- cross-tenant não enumera recurso;
- conteúdo, locator, hashes, source metadata e trust digest ausentes;
- self-approval, stale, revoked, policy failure e collision possuem reasons
  fechados.

### PostgreSQL e migration

- round-trip completo e ordenado;
- todas as candidate keys, checks e FKs;
- predecessor errado, sequência duplicada e bifurcação recusados;
- cross-tenant/cross-Investigation/cross-Company/cross-decision recusados;
- FK recusa `evidence_series_id` divergente com `evidence_id` válido;
- FK recusa `evidence_version` divergente com `evidence_id` válido;
- mapper/reconstituição recusam os mesmos dois tampers;
- `valid_until` incompatível recusado;
- mapper rejeita adulteração;
- downgrade protegido e dados existentes preservados;
- `alembic check` e metadata convergence;
- guard transacional sem autobegin/reuso.

### Regressão F5.1

- suíte F5.1 integral sem relaxamento;
- Evidence persistida permanece `PENDING`;
- Artifact, digests, locators, correção e revogação inalterados;
- revogação permanece evento F5.1 terminal;
- migrations anteriores não são reescritas;
- corridas Evidence×Evidence continuam válidas.

### Regressão F5.2

- suíte F5.2 integral sem relaxamento;
- Claim e `ClaimEvidenceLink` não ganham campo ou update;
- assessment continua contextual e derivado;
- `ELIGIBLE` nunca promove Evidence;
- manifesto F5.2 e digest permanecem inalterados;
- locks Claim×Evidence continuam válidos;
- nenhuma revisão factual ou Claim crítica é implementada.

### Arquitetura

- domínio de Evidence não importa aplicação, infraestrutura, orchestration,
  claims, connectors, risk, reporting ou interfaces;
- policy cross-aggregate permanece na aplicação;
- repositório não possui commit/rollback/update/delete;
- exatamente uma tabela e uma migration novas;
- ausência de HTTP, lifecycle, F5.4, fonte real, IA, risco e relatório.

## Cobertura futura

- módulos novos de admissibilidade: pelo menos 90% de branch coverage;
- invariantes críticas, todos os statuses e outcomes: 100% exercitados;
- cobertura global: pelo menos o gate vigente, nunca abaixo de 80% de linhas;
- nenhum skip de teste crítico sem aceite explícito;
- nenhuma linha irrelevante adicionada apenas para elevar cobertura.

## Documentação futura

No mesmo conjunto autorizado de implementação:

- manter ADR 0026 `Proposed` até revisão independente;
- atualizar contrato de evidências, data model, segurança e `PLANS.md` sem
  redefinir F5.2;
- registrar policy/manifest IDs, versões, digests e fixtures reais da entrega;
- registrar a ausência de fonte real, G6 e runtime path até `VERIFYING`;
- criar validação F5.3 com comandos e resultados reais;
- não declarar F5.4 ou Gate G4 concluídos.

## Validações e gates futuros

1. instalação frozen sem dependência nova;
2. lint e formatação Python/Markdown aplicáveis;
3. mypy estrito e TypeScript;
4. scanner de segredos;
5. testes focais de Evidence/admissibilidade;
6. regressões F5.1 e F5.2;
7. integração PostgreSQL real controlada;
8. migration upgrade/check/downgrade protegido/re-upgrade;
9. concorrência repetida;
10. suíte integral Python e web;
11. builds Python/web;
12. coverage gates;
13. `git diff --check`;
14. revisão de arquitetura e threat model;
15. pacote limpo somente com arquivos rastreados;
16. revisão independente binária.

Falhas, warnings e incidentes intermediários devem ser registrados sem
conversão artificial em sucesso.

## Critérios de aceite da implementação

1. Uma versão corrente de Evidence recebe decisões append-only reproduzíveis.
2. Status inicial persistido permanece `PENDING` e status efetivo é derivado.
3. `as_of` controla deterministicamente expiração, existência e história sem
   tratar corte anterior à Evidence como `PENDING`.
4. Somente `ADMISSIBLE` expira; revogação F5.1 domina e é terminal.
5. Correção começa `PENDING` e não herda decisão.
6. Trust root F5.3 é próprio, sintético, rastreável e recomputável.
7. Manifesto F5.2, source ID e origin type nunca bastam para `ADMISSIBLE`.
8. Nenhuma fonte real é admissível na V1 e G6 não é simulado.
9. Outcome/policy/purpose/manifest/time não vêm prontos do comando.
10. Self-approval positivo é bloqueado pela autoria da versão exata.
11. OWNER/ADMIN decidem; ANALYST/VIEWER somente leem.
12. FK e mapper vinculam Evidence ID/series/version/contexto à mesma linha real.
13. Toda decisão pertence ao intervalo histórico decidível da versão.
14. A V1 não contém freshness oculto nem prazo automático.
15. Replay reutiliza `decision.decided_at`, sem Clock ou expiração retroativa.
16. Todas as decisões V1 preservam trust-root snapshot; negativo não implica
    match positivo.
17. História, tenancy, digests, replay e concorrência falham fechado.
18. Uma tabela, uma porta e uma migration append-only são suficientes.
19. Decisão e audit de sucesso compartilham commit e permanecem redigidos.
20. F5.1 e F5.2 passam integralmente sem alteração semântica.
21. Não há Claim review, critical gate, lifecycle ou capacidade posterior.
22. Todos os gates estáticos, builds, PostgreSQL, migration e coverage passam.
23. Revisão independente emite `APPROVED` ou `APPROVED_WITH_FIXES` e autoriza a
    promoção do ADR 0026.

## Critérios de bloqueio

Bloquear implementação ou fechamento se ocorrer qualquer item:

- alteração direta de `Evidence.admissibility_status`;
- tabela/cache/trigger de status efetivo;
- decisão apontando para `latest` implícito;
- FK que deixe Evidence series/version desacoplados do ID/contexto real;
- mapper que aceite series/version adulterados;
- decisão herdada após correção;
- nova decisão em Evidence superseded ou revoked;
- decisão anterior à criação ou em/após supersession/revocation;
- efeito retroativo de supersession/revocation;
- `REVOKED` escolhido por comando;
- `EXPIRED` escolhido por ator ou relógio escondido;
- `RESTRICTED`/`REJECTED` expirando automaticamente;
- regra implícita de freshness, atualidade comercial ou validade por categoria;
- prazo automático não definido pela policy;
- manifesto F5.2 suficiente para `ADMISSIBLE`;
- source metadata textual concedendo confiança;
- fonte real admitida ou aprovação G6 inventada;
- magic hash, fixture ausente ou canonicalização divergente da F5.1;
- comando aceitando outcome, policy, purpose, manifest, time ou digest pronto;
- replay lendo Clock atual ou recalculando a operação após expiration;
- `PENDING` devolvido para corte anterior à criação da Evidence;
- trust-root snapshot nulo em qualquer outcome da policy V1;
- snapshot negativo interpretado como match positivo;
- `ADMIT` negado convertido silenciosamente em outcome negativo;
- self-approval positivo;
- criação de `last_corrector`, `REVIEWER` ou `PROPOSE` sem nova decisão;
- ANALYST/VIEWER ganhando mutação;
- update/delete/save/replace ou commit no repositório;
- predecessor, sequence ou FKs não protegendo tenant/contexto;
- ausência de lock/revalidação contra correction/revoke;
- conteúdo, locator, hash ou source metadata vazando em audit/log/erro;
- migration F5.1/F5.2 reescrita ou histórico perdido;
- alteração de Claim/link/assessment F5.2;
- Claim review, critical gate, lifecycle, F5.4 ou Gate G4 antecipados;
- fonte real, HTTP, jobs, IA, risco, scoring ou relatório;
- teste crítico falho/skipped, type error, segredo ou migration divergente;
- ADR 0026 marcado `Accepted` antes da revisão independente.

## Gate G4 e F5.4

A F5.3 não fecha o Gate G4. Ela fornece somente a admissibilidade global
necessária para uma futura avaliação factual.

A F5.4 continuará necessária para:

- `ClaimReviewDecision`;
- operação de aceite para uso factual;
- bloqueio de Claims críticas;
- tratamento de `CONTRADICTS + ADMISSIBLE`;
- revisão humana factual.

F5.4 permanece `NOT_STARTED` e `NOT_AUTHORIZED`.

## Instruções para revisão independente

O pacote candidato futuro deverá ser revisado sem assumir que a suíte existente
é suficiente. O revisor deverá:

1. confirmar baseline, autorização, migrations e diff exato;
2. recomputar todas as âncoras e o manifest digest da F5.3;
3. provar que manifesto F5.2 e source metadata não admitem;
4. provar que nenhuma fonte real admite na policy V1;
5. revisar modelo, história, projeção `as_of`, porta e UoW;
6. reproduzir self-approval, tenancy, stale e tamper;
7. reproduzir corridas contra correction/revoke e entre decisões;
8. comprovar replay sem ID/clock/audit novo e collision fail-closed;
9. inspecionar PostgreSQL, migration e downgrade protegido;
10. confirmar que Evidence persistida continua `PENDING`;
11. executar regressões F5.1/F5.2 e gates integrais;
12. revisar redaction, segurança e ausência de escopo posterior;
13. confirmar que F5.4/G4 continuam abertos;
14. classificar o gate como `APPROVED`, `APPROVED_WITH_FIXES` ou `BLOCKED`.

## Estado deste draft

- ADR 0026: `Proposed`;
- implementação: `NOT_STARTED`;
- migration: inexistente;
- testes: não escritos;
- F5.4: `NOT_STARTED / NOT_AUTHORIZED`;
- Gate G4: aberto;
- fonte real/G6: não iniciados.
