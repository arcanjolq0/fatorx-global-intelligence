# ADR 0026 — Decisões globais de admissibilidade de Evidence

- Status: Proposed
- Data: 2026-08-22
- Decisores: responsável pelo projeto e futura revisão independente da F5.3
- Relacionados: ADR 0003, ADR 0007, ADR 0008, ADR 0011, ADR 0013, ADR 0024 e ADR 0025

## Contexto

A F5.1 materializou `Artifact`, versões imutáveis de `Evidence` e eventos
append-only de supersessão e revogação. Toda versão possui cadeia de custódia,
hash, locator, fonte e política em snapshot, temporalidade, vínculo com a
Company confirmada e `Evidence.admissibility_status = PENDING`. O ADR 0024
proíbe atualizar essas linhas para decidir admissibilidade.

A F5.2 materializou Claims estruturadas, links para versões exatas de Evidence
e `ClaimEvidenceUseDecision`. Seu outcome `ELIGIBLE` responde somente se aquela
Evidence pode participar da verificação interna daquela Claim sob
`INTERNAL_CLAIM_VERIFICATION` e o manifesto sintético controlado da F5.2. Ele
não aprova a Evidence, não torna a Claim factual e não satisfaz o Gate G6.

O contrato de evidências já reserva os estados globais `PENDING`, `ADMISSIBLE`,
`RESTRICTED`, `EXPIRED`, `REVOKED` e `REJECTED`, mas ainda não existe decisão
global, política de admissão, status efetivo ou autoridade humana para aplicá-los.
Também não há fonte real, catálogo G6, transição runtime até `VERIFYING`, revisão
factual de Claim ou operação de publicação.

## Problema

A próxima unidade precisa decidir a admissibilidade de uma versão exata de
Evidence sem:

- atualizar a Evidence imutável ou reinterpretar seu status inicial;
- promover automaticamente um outcome F5.2;
- tratar admissibilidade como permissão universal de uso;
- confiar em texto de origem, prefixos ou metadados controláveis pelo envelope;
- simular aprovação de fonte real ou Gate G6;
- permitir autoaprovação positiva do autor da Evidence;
- perder decisões anteriores depois de reversão, correção, expiração ou revogação;
- misturar revisão de Evidence, Claim, risco e relatório em um registro genérico;
- antecipar lifecycle, revisão factual de Claim ou F5.4.

## Decisão

### 1. Fronteira da F5.3

A F5.3 materializará somente:

1. `EvidenceAdmissibilityDecision` append-only;
2. política de admissibilidade V1;
3. raiz de confiança sintética própria;
4. projeção `EffectiveEvidenceAdmissibility`;
5. comando e caso de uso internos;
6. autorização, auditoria, idempotência e concorrência;
7. porta, adapter PostgreSQL, uma tabela e uma migration futura;
8. testes proporcionais ao risco.

Não pertencem à F5.3 `ClaimReviewDecision`, aprovação ou factualidade de Claim,
gate de Claim crítica, conflito factual, papel `REVIEWER`, proposta por analyst,
transições de Investigation, relatório, exportação, risco, scoring, IA, fonte
real ou Gate G6.

### 2. Semântica de “global” e finalidade V1

“Global” significa que a decisão pertence à própria versão de Evidence e não a
um link ou a uma Claim específica. Não significa autorização para todo uso.

A finalidade fechada V1 é:

`INTERNAL_FACTUAL_EVIDENCE_USE`

`ADMISSIBLE` significa exclusivamente:

> Esta versão exata da Evidence é admissível para
> `INTERNAL_FACTUAL_EVIDENCE_USE` sob a política de admissibilidade V1.

Essa decisão não autoriza automaticamente relatório, exportação,
redistribuição, publicação externa, uso por modelo, risco, scoring, crédito ou
qualquer finalidade diferente.

A separação obrigatória é:

- F5.2: `ELIGIBLE` para `INTERNAL_CLAIM_VERIFICATION`;
- F5.3: `ADMISSIBLE` para `INTERNAL_FACTUAL_EVIDENCE_USE`.

`ELIGIBLE` nunca promove Evidence para `ADMISSIBLE`, nem é precondição
suficiente para isso.

### 3. Status inicial persistido e status efetivo

`Evidence.admissibility_status` permanece `PENDING` no domínio, digest, mapper,
tabela e constraint F5.1. Nenhum serviço da F5.3 atualiza essa linha.

O status corrente é uma projeção de leitura, nunca coluna, cache ou evento
autônomo. `EffectiveEvidenceAdmissibility` recebe a história integral da série,
a história de decisões e um instante explícito `as_of`. Antes de calcular um
status, ela comprova que a série já existia naquele corte. `as_of` anterior a
`created_at` da primeira versão representa recurso ainda inexistente, não
`PENDING`, e deve produzir ausência/erro tipado conforme o padrão da aplicação.

Depois da existência da série, a projeção seleciona a versão corrente no corte
e calcula:

- `PENDING`: nenhuma decisão aplicável para a versão corrente;
- `ADMISSIBLE`: última decisão aplicável é positiva e ainda vigente;
- `RESTRICTED`: última decisão aplicável é restritiva;
- `REJECTED`: última decisão aplicável é rejeição;
- `EXPIRED`: somente uma decisão positiva possuía `valid_until` e expirou;
- `REVOKED`: a história F5.1 possui revogação terminal aplicável no corte.

A projeção não usa `datetime.now()` ou relógio escondido no domínio. A camada de
aplicação fornece `as_of` diretamente ou por `Clock` controlado.

Supersessão e revogação produzem efeitos somente em cortes iguais ou posteriores
ao `occurred_at` do evento F5.1. Não possuem efeito retroativo: uma leitura
anterior ao evento continua selecionando a versão e a decisão então aplicáveis.

Toda decisão reconstituída deve cair no intervalo em que sua versão existia e
ainda era decidível: `decided_at >= Evidence.created_at`,
`decided_at < SUPERSEDED.occurred_at` quando a versão foi superseded e
`decided_at < REVOKED.occurred_at` quando a revogação é aplicável. Persistência
que viole esse intervalo falha fechado.

### 4. Expiração V1

Somente uma decisão `ADMISSIBLE` pode possuir `valid_until`. Quando
`as_of >= valid_until`, seu status efetivo passa a `EXPIRED`.

`RESTRICTED` e `REJECTED` não expiram automaticamente e devem ter
`valid_until = None`. Eles mudam somente por decisão superseding. `PENDING` não
expira. `REVOKED` é terminal e dominante.

Uma nova admissão de Evidence anteriormente expirada é possível somente por
outra decisão append-only, enquanto a versão continuar corrente e não revogada,
com a política integralmente reaplicada.

A V1 não define threshold genérico de freshness, atualidade comercial ou
validade por categoria e não inventa prazo automático. `ADMISSIBLE` pode ter
`valid_until = None`. Quando o comando positivo solicitar validade, a política
exige `requested_valid_until > decided_at`; valor igual ou anterior é rejeitado.
Freshness de fonte ou categoria exige versão posterior da política.

### 5. Raiz de confiança V1

A base fechada V1 é:

`CONTROLLED_TEST_EVIDENCE`

Ela reconhece somente corpus sintético rastreado no repositório. A futura
implementação terá namespace, policy ID, manifest ID/version e digest próprios
da F5.3. Poderá reutilizar SHA-256, `locator_to_canonical_json` e uma estrutura
semelhante a `ControlledEvidenceAnchorV1`, mas não duplicará a canonicalização
F5.1.

A âncora sintética mínima combinará exatamente:

- hash dos bytes originais do Artifact;
- hash do conteúdo localizado da Evidence;
- kind da Evidence;
- tipo do locator;
- digest do locator canônico.

Toda decisão produzida pela política V1, inclusive `RESTRICTED` e `REJECTED`,
registra o manifest/trust-root ID adotado pelo modelo final, version e digest,
além de policy ID/version, purpose e admission basis. O snapshot identifica o
contexto exato em que a política foi executada; para uma decisão negativa, ele
não afirma que a Evidence correspondeu positivamente a uma âncora.

`F5_2_CONTROLLED_CORPUS_MANIFEST_V1` não é raiz de confiança da F5.3 e nunca é
prova suficiente para `ADMISSIBLE`. `source_id`, `origin_type`, filename,
`acquisition_method`, prefixos e labels também não concedem confiança.

Nenhuma fonte real pode resultar `ADMISSIBLE` na política V1. Não será criado
enum ou registro fictício de aprovação G6. Quando um catálogo real existir, uma
nova versão da política poderá exigir referência verificável à aprovação
técnica, jurídica e comercial correspondente.

### 6. Política V1

A política será identificada como:

`F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1`

Para produzir `ADMISSIBLE`, ela exigirá cumulativamente:

1. `EvidenceHistory` íntegra;
2. Evidence alvo como versão corrente da série;
3. ID, versão e digest exatos;
4. workspace, Investigation, Company e decisão de entidade coerentes;
5. ausência de supersessão e revogação aplicáveis;
6. Artifact íntegro e do mesmo escopo;
7. match único e exato na raiz sintética F5.3;
8. storage `EXCERPT_ONLY`, retention `INDEFINITE` e display `FULL` na V1;
9. `content_original` presente, verificável e coerente com seu hash;
10. timestamps e invariantes temporais F5.1 íntegros;
11. `decided_at >= Evidence.created_at` e anterior a qualquer supersessão ou
    revogação aplicável;
12. `requested_valid_until > decided_at`, quando fornecido, sem prazo automático;
13. policy ID/version, purpose e admission basis canônicos;
14. separação de funções;
15. nenhuma precondição material desconhecida.

Não há regra implícita de freshness, atualidade comercial ou validade por
categoria na V1. Esses critérios pertencem a uma nova versão de policy.

Falha de integridade, adulteração, escopo divergente ou versão obsoleta é erro
fail-closed, não outcome normal. Uma tentativa positiva que não satisfaça todos
os requisitos falha; ela não é convertida silenciosamente em `RESTRICTED`.

Decisões negativas não estabelecem confiança de fonte e não tornam material
real autorizado. A razão informada deve ser fechada e compatível com a ação.

### 7. Ação solicitada e outcome persistido

O comando recebe uma `requested_action` fechada:

- `ADMIT`;
- `RESTRICT`;
- `REJECT`.

A aplicação e a política produzem respectivamente:

- `ADMISSIBLE`;
- `RESTRICTED`;
- `REJECTED`.

O ator não fornece o objeto persistido nem policy ID/version, purpose, admission
basis, manifest ID/version/digest, `decided_at`, outcome, status efetivo ou
decision digest.

O comando poderá fornecer somente IDs e digests esperados, ação, razão fechada
compatível e, para `ADMIT`, um `requested_valid_until` opcional que a política
validará contra `decided_at` antes de produzir o valor persistido.

### 8. EvidenceAdmissibilityDecision

O registro imutável conterá:

- ID;
- workspace, Investigation, Company e decisão de resolução de entidade;
- Evidence ID, series ID, versão e digest exatos;
- sequência positiva;
- ID da decisão superseded;
- outcome e reason code fechados;
- policy ID/version;
- purpose e admission basis;
- manifest/trust-root ID, version e digest obrigatórios na policy V1;
- `valid_until` somente quando permitido;
- command ID/digest;
- ator e instante da decisão;
- schema version e decision digest.

Não conterá conteúdo bruto, locator integral, ClaimValue, justificativa livre,
origem textual usada como confiança ou payload arbitrário.

### 9. História, correção e reversão

A primeira decisão usa `decision_sequence = 1` e
`supersedes_decision_id = None`. Cada decisão posterior possui sequência
contígua e supersede exatamente a decisão imediatamente anterior da mesma
versão de Evidence.

Toda reversão é nova decisão. Não existem update, delete ou comando para voltar
a `PENDING`.

Uma correção F5.1 cria nova versão de Evidence, que começa efetivamente
`PENDING`. Decisões da versão anterior permanecem históricas e não são herdadas.
Uma versão superseded não aceita novas decisões.

Cada decisão deve satisfazer o intervalo histórico da versão alvo. A operação
normal comprova isso sob lock; `EvidenceAdmissibilityHistory` e a projeção
repetem a validação para detectar decisão adulterada anterior à criação ou em
instante igual/posterior à supersessão ou revogação.

### 10. Self-approval

Para `requested_action = ADMIT`, `decided_by` deve ser diferente de
`created_by` da versão exata da Evidence alvo. Como cada correção gera versão
com seu próprio `created_by`, nenhum campo adicional de “last corrector” será
criado.

`RESTRICT` e `REJECT` podem ser executados pelo criador porque são fail-safe.
Qualquer reversão para `ADMISSIBLE` reaplica a separação. Mudança futura dessa
regra exige nova versão de política.

Não será criado papel `REVIEWER`. OWNER e ADMIN decidem; ANALYST e VIEWER apenas
leem.

### 11. Revogação

`REVOKED` não é outcome de `EvidenceAdmissibilityDecision`. Ele deriva do
`EvidenceLifecycleEvent` terminal F5.1 e prevalece sobre qualquer decisão
aplicável no mesmo instante de corte.

Depois da revogação não há nova decisão. Decisões anteriores continuam
reproduzíveis em leituras históricas cujo `as_of` anteceda a revogação.
Supersessão e revogação não invalidam retroativamente decisões que eram
aplicáveis antes do respectivo `occurred_at`.

### 12. Lifecycle da Investigation

Nova decisão exige snapshot da Investigation já em `VERIFYING`. A F5.3 não
implementa `COLLECTING -> NORMALIZING`, `NORMALIZING -> VERIFYING` nem qualquer
outra transição.

Leitura histórica poderá ocorrer em `VERIFYING`, `ANALYZING`,
`WAITING_FOR_REVIEW`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED` e
`CANCELLED`, sem restaurar estado anterior.

O fluxo runtime continuará sem caminho normal materializado até `VERIFYING`.
Testes poderão reconstituir snapshots válidos, sem abrir exceção para decidir em
`COLLECTING`.

### 13. Persistência e porta

Uma única tabela futura, `evidence_admissibility_decision`, preservará a
história. Não haverá tabela de status efetivo nem alteração de Evidence, Claim
ou `ClaimEvidenceLink`.

A FK para Evidence deve provar que `evidence_id`, `evidence_series_id`,
`evidence_version`, workspace, Investigation, subject Company e decisão de
resolução pertencem à mesma linha real. Validar apenas Evidence ID e contexto,
deixando series/version livres, é proibido.

A migration futura inspecionará as candidate keys existentes de `evidence` e
reutilizará uma chave somente se ela cobrir todos esses campos. Caso contrário,
adicionará à tabela F5.1 apenas a candidate key composta estritamente necessária
para uma FK tenant-first completa, sem editar migrations anteriores.

Além disso, a tabela terá PK própria, candidate keys tenant-scoped para comando
e sequência, FK composta do predecessor para a mesma versão de Evidence, checks
de sequência, predecessor, outcome/reason, `valid_until`, política, finalidade,
base, schema e digests, e índices tenant-first por comando, Evidence e
Investigation.

Não haverá cascade destrutiva. Downgrade futuro deverá recusar perda de
histórico quando houver decisões.

A porta `EvidenceAdmissibilityDecisionRepository` terá somente:

- `acquire_command_lock`;
- `acquire_history_lock`;
- `add_initial`;
- `add_superseding`;
- `get_history`;
- `get_history_by_command`.

Commit e rollback pertencem exclusivamente à Unit of Work.

### 14. Concorrência e atomicidade

A ordem obrigatória será:

1. command lock tenant-scoped;
2. Evidence history lock;
3. admissibility decision history lock;
4. releitura integral;
5. validação;
6. execução da política;
7. construção completa;
8. append;
9. auditoria;
10. commit único.

Decisão contra correção/revogação de Evidence e duas decisões sobre a mesma
versão serão serializadas. A operação bem-sucedida fixa
`operation_as_of = decision.decided_at` e devolve a história, a projeção calculada
nesse corte e `replayed`.

Replay idêntico não gera novo ID, lê Clock, cria auditoria nem recalcula o
resultado usando o tempo corrente. Ele reutiliza o `decided_at` persistido e
devolve semanticamente o resultado histórico original. Assim, uma admissão em
T1 com `valid_until = T2` continua retornando `ADMISSIBLE` no replay executado
depois de T2, pois seu `operation_as_of` permanece T1. Uma leitura separada com
`as_of = T3` é necessária para obter `EXPIRED`. Reuso do command ID com digest
divergente falha fechado.

O serviço de admissibilidade não adquire lock de Claim. Uma futura revisão de
Claim deverá respeitar a direção Claim → Evidences ordenadas → decisões de
admissibilidade para não introduzir ciclo.

### 15. Autorização

| Papel   | Read | Admit | Restrict | Reject | Supersede |
| ------- | ---: | ----: | -------: | -----: | --------: |
| OWNER   |  sim |   sim |      sim |    sim |       sim |
| ADMIN   |  sim |   sim |      sim |    sim |       sim |
| ANALYST |  sim |   não |      não |    não |       não |
| VIEWER  |  sim |   não |      não |    não |       não |

`ADMIT` continua sujeito à separação de funções. Não existe `PROPOSE`.
Workspace vem somente do `ActorContext`; lookup e locks são tenant-first.

### 16. Auditoria

Enquanto o schema vigente não exigir novo resource type, a auditoria usará
`INVESTIGATION`. Ações e reasons serão fechados para decidir e superseder
admissibilidade e para negação/falha conhecida.

Sucesso compartilha o commit da decisão. Negação e falha conhecida seguem o
padrão standalone aceito. Recurso cross-tenant permanece não enumerável.

Auditoria não recebe conteúdo, locator, hashes, source metadata, justificativa
livre, manifest digest ou payload arbitrário. A tabela de decisão preserva a
trilha detalhada necessária.

### 17. Tenancy e segurança

- o workspace efetivo vem exclusivamente do ator autorizado;
- FKs compostas repetem workspace, Investigation, Company e decisão;
- FK e reconstituição vinculam Evidence ID, series ID, version e todo o contexto
  à mesma linha real;
- Evidence digest exato impede aprovação stale;
- decisão positiva não pode ser feita pelo autor da versão;
- comando não controla outcome, política, trust root ou instante;
- source snapshots e manifesto F5.2 não concedem admissão;
- reconstituição recalcula digests e falha fechado;
- decisões fora do intervalo de existência da versão falham fechado;
- toda decisão V1 preserva policy/purpose/basis e trust-root snapshot, sem
  transformar snapshot negativo em match positivo;
- histórias são append-only e sem deleção destrutiva;
- erros, logs, `repr` e auditoria permanecem redigidos;
- não há rede, filesystem runtime, source real, segredo ou conteúdo executável.

### 18. Revisão factual e Claims críticas

A F5.3 não cria `ClaimReviewDecision`, não bloqueia `RegisterClaim` e não marca
Claim como factual. Ela fornece apenas o status de admissibilidade que uma
futura F5.4 consumirá.

O gate futuro deverá exigir, no mínimo, uma versão corrente
`SUPPORTS + ADMISSIBLE`, não expirada nem revogada, e tratar toda Evidence
`CONTRADICTS + ADMISSIBLE`. A decisão humana factual e a invalidação corrente da
Claim pertencem à F5.4.

### 19. Gate G4

A F5.3 não fecha o Gate G4. F5.1 já entrega cadeia de custódia e F5.2 já entrega
Claims, links e contradição contextual. Ainda serão necessários
`ClaimReviewDecision`, gate de uso factual, bloqueio de Claims críticas,
tratamento de contradições admissíveis e revisão humana factual em uma F5.4.

## Consequências

- A Evidence permanece imutável e a decisão global ganha história própria.
- O status efetivo reage a corte temporal, correção e revogação sem update.
- Ausência anterior à criação não é confundida com `PENDING`.
- Replay preserva o cutoff e o resultado histórico da operação original.
- Admissibilidade fica separada de elegibilidade contextual e de aprovação de
  Claim.
- Corpus sintético permite validar a arquitetura sem inventar fonte real.
- Separação de funções impede a promoção positiva pelo autor da versão.
- Uma tabela e uma porta especializadas evitam um workflow genérico prematuro.
- O caso de uso continuará inalcançável pelo fluxo runtime normal até que a
  orchestration materialize a entrada em `VERIFYING`.
- A F5.4 e o Gate G4 permanecem explicitamente abertos.

## Alternativas rejeitadas

- **Atualizar `Evidence.admissibility_status`:** viola a imutabilidade F5.1 e
  destrói a distinção entre snapshot inicial e decisão.
- **Reutilizar `ELIGIBLE`:** confunde finalidade contextual F5.2 com uso factual
  interno.
- **Usar o manifesto F5.2 como trust root:** permite promoção por uma raiz que
  nunca foi aprovada para admissibilidade.
- **Confiar em source metadata textual:** campos do envelope não provam corpus,
  licença ou autenticidade.
- **Permitir fonte real na V1:** inventa aprovação G6 inexistente.
- **Persistir status efetivo:** cria estado obsoleto e exige atualização após
  tempo, correção ou revogação.
- **Tratar `EXPIRED` como ação humana:** mistura passagem do tempo com decisão.
- **Representar `REVOKED` como decisão:** duplica e conflita com o lifecycle F5.1.
- **Herdar decisão após correção:** admite conteúdo ou locator que não foi
  revisado.
- **Permitir decisão em versão superseded:** cria uma promoção sem efeito
  corrente e favorece laundering.
- **Criar `ReviewDecision` polimórfica:** mistura semânticas de agregados
  diferentes e antecipa F5.4.
- **Criar papel `REVIEWER` ou proposal:** amplia identidade e workflow sem
  necessidade para a unidade.
- **Misturar transições até `VERIFYING`:** acopla orchestration à decisão de
  evidência.

## Itens adiados

- implementação da própria F5.3, dependente de autorização posterior;
- fonte real, catálogo de fontes e Gate G6;
- política de admissibilidade posterior para fontes aprovadas;
- transições até `VERIFYING`;
- `ClaimReviewDecision` e revisão factual;
- gate de Claims críticas e tratamento de conflitos;
- relatório, exportação e redistribuição;
- risco, scoring, IA e crédito;
- HTTP, frontend, jobs, workers, filas, scheduler e outbox;
- fechamento do Gate G4.

## Critérios objetivos de aceite futuro

O status deste ADR só poderá mudar para `Accepted` depois que uma implementação
explicitamente autorizada comprovar:

1. Evidence F5.1 e seu status persistido continuam inalterados e `PENDING`;
2. uma única tabela append-only e uma porta sem commit/update/delete;
3. status efetivo reproduzível com `as_of` explícito e ausência tipada antes da
   criação da série;
4. `EXPIRED` somente para admissão positiva vencida e `REVOKED` dominante;
5. correção inicia nova versão `PENDING` sem herança de decisão;
6. manifesto F5.2, source ID e origin type nunca são suficientes para admissão;
7. trust root F5.3 próprio, sintético, rastreável e recomputável;
8. nenhuma fonte real resulta `ADMISSIBLE` na V1;
9. outcome, política, finalidade, manifest e instante não vêm prontos do comando;
10. self-approval positivo é bloqueado pela autoria da versão exata;
11. owner/admin decidem e analyst/viewer somente leem;
12. FK e mapper vinculam ID, series, version e contexto à mesma Evidence real;
13. decisões fora do intervalo histórico da versão falham fechado;
14. replay reutiliza `decision.decided_at` e não consulta Clock corrente;
15. toda decisão V1, positiva ou negativa, preserva o trust-root snapshot;
16. tenancy, tamper, idempotência, replay e concorrência falham fechado;
17. decisão e auditoria de sucesso são atômicas e redigidas;
18. nenhuma revisão de Claim, lifecycle ou capacidade posterior foi criada;
19. regressões F5.1/F5.2, PostgreSQL, migration, tipos, lint, cobertura, scanner,
    builds e pacote limpo foram aprovados;
20. revisão independente emitiu parecer binário de aceite.

Até esse gate, este ADR permanece `Proposed`, a implementação permanece
`NOT_STARTED` e o Gate G4 permanece aberto.
