# F5.2 — Claims e elegibilidade contextual de evidência

## Status

**ACEITA APÓS REVISÃO INDEPENDENTE COM CORREÇÕES EM 2026-08-22.**

O scoping foi aprovado e a autorização explícita de 2026-08-21 permitiu código,
testes, migration e checkpoint candidato exclusivamente para F5.2. A revisão
independente de 2026-08-22 aceitou a implementação com correções e promoveu o
ADR 0025 a `Accepted`; F5.3 continua não autorizada.

## Objetivo

Materializar a menor fronteira de claims coerente com a F5.1:

- Claim estrutural, imutável, tenant-scoped e versionada;
- vínculo explícito com versões exatas de Evidence;
- decisão contextual de uso separada da admissibilidade global da Evidence;
- assessment corrente derivado e fail-closed;
- persistência append-only em somente duas tabelas;
- autorização, idempotência, auditoria e concorrência proporcionais ao risco.

A estratégia arquitetural de corpus controlado foi definida no ADR 0025,
materializada e aprovada na revisão independente.

## Baseline obrigatório

Antes de qualquer futura implementação, confirmar:

- branch autorizada pelo responsável;
- baseline mínimo `05064e2a82aeca28504b0ce1359f0f839fda1c23` ou sucessor
  explicitamente aprovado;
- tag `f5.1-final` preservada;
- F5.1 `CLOSED — APPROVED_WITH_FIXES`;
- ADR 0024 `Accepted`;
- ADR 0025 ainda `Proposed` até revisão independente;
- working tree limpa ou alterações existentes identificadas e preservadas;
- nenhuma migration posterior concorrente sem reconciliação de revision.

Se HEAD, árvore, migrations ou autorização divergirem, parar e reportar antes
de alterar arquivos.

## Pré-condições de implementação

São obrigatórias:

1. autorização explícita para implementar somente F5.2;
2. autorização explícita para materializar o manifesto interno imutável
   `F5_2_CONTROLLED_CORPUS_MANIFEST_V1` conforme o ADR 0025;
3. confirmação independente das âncoras sintéticas admitidas, das fixtures que
   as originam e do digest canônico do manifesto, sem representar aprovação de
   fonte real ou Gate G6;
4. confirmação de que o caso de uso continuará restrito a `VERIFYING` mesmo sem
   transição runtime materializada;
5. revisão dos arquivos e migrations criados depois desta proposta;
6. manutenção do limite de duas tabelas e nenhuma dependência nova.

### Decisão de corpus adotada

F5.1 não possui marcador confiável de corpus controlado. Por isso, a F5.2 usará
o manifesto interno, imutável e versionado
`F5_2_CONTROLLED_CORPUS_MANIFEST_V1`, composto por
`ControlledEvidenceAnchorV1`. Cada âncora vincula hash do Artifact, hash e kind
do conteúdo localizado e locator canônico. Hash de Artifact isolado,
`source.synthetic.business_registry`, prefixos, nomes de arquivo, `origin_type`
ou `acquisition_method` não podem ser usados como prova.

O bloqueador conceitual foi resolvido pelo scoping arquitetural. A implementação
continua `NOT_STARTED` e deve ser bloqueada se divergir do manifesto, aceitar
entrada controlada por comando/runtime ou atribuir qualquer significado de
aprovação G6.

## Escopo

### Incluído

- pacote de domínio puro `intelligence.claims`;
- predicates estruturais V1 e valores tipados;
- Claim versionada e `ClaimHistory` fail-closed;
- `ClaimEvidenceLink` muitos-para-muitos;
- `ClaimEvidenceUseDecision` com `ELIGIBLE`, `RESTRICTED`, `REJECTED`;
- roles `SUPPORTS`, `CONTRADICTS`, `QUALIFIES`;
- assessment corrente `INSUFFICIENT`, `SUPPORTED`, `CONFLICTED`;
- registro e correção somente em `VERIFYING`;
- leitura tenant-scoped em estados compatíveis;
- owner/admin para registro/correção e seleção do role semântico;
- analyst/viewer somente leitura;
- idempotência e locks tenant-scoped;
- auditoria coordenada e redigida;
- adapter PostgreSQL e migration nova futura;
- testes unitários, integração, migration, concorrência, segurança e arquitetura;
- documentação e validação próprias da F5.2.

### Fora de escopo

- alteração de `Evidence.admissibility_status=PENDING`;
- admissibilidade global, expiração ou novo lifecycle de Evidence;
- Claim em `COLLECTING`;
- `NORMALIZING -> VERIFYING` ou qualquer transição de Investigation;
- status `TRUE`, `FALSE`, `FACTUAL`, `APPROVED`, `REPORTABLE`, `REFUTED`,
  `SCORED` ou risco;
- proposta por analyst, papel reviewer ou workflow de aprovação;
- rejeição humana de Claim e `ReviewDecision` genérica;
- consulta histórica `as of`, cache ou snapshot de assessment;
- grupos globais de conflito, precedência ou escolha de verdade;
- predicates de sanção, fraude, litígio, reputação, crédito, risco ou score;
- extração automática, OCR, tradução, modelo ou IA;
- fonte/conector real, catálogo G6 ou storage de objetos;
- HTTP, API, frontend, jobs, workers, filas, scheduler, outbox ou paralelismo;
- risco, scoring, relatório, exportação e F5.3.

## Componentes e arquivos previstos

Os nomes finais devem seguir a organização vigente. O conjunto esperado é:

### Domínio

- `src/intelligence/claims/__init__.py`;
- `src/intelligence/claims/models.py`;
- `src/intelligence/claims/errors.py`;
- identificadores fortes adicionais em
  `src/intelligence/domain/identifiers.py`.

### Aplicação

- contratos de comando/resultado em `src/intelligence/application/claims.py`;
- manifesto imutável e política determinística em
  `src/intelligence/application/claim_evidence_policy.py`;
- serviço em `src/intelligence/application/services/claims.py`;
- extensão pequena das portas em
  `src/intelligence/application/ports/repositories.py`;
- propriedade correspondente em
  `src/intelligence/application/ports/unit_of_work.py`;
- permissões fechadas em `src/intelligence/application/authorization.py`;
- ações/razões fechadas em `src/intelligence/application/audit.py`;
- erros públicos tipados em `src/intelligence/application/errors.py`.

### Persistência

- metadata `claim` e `claim_evidence_link` em arquivo próprio PostgreSQL;
- mappers próprios;
- `PostgreSQLClaimRepository` próprio;
- composição na PostgreSQL Unit of Work;
- exports explícitos de infraestrutura;
- migration nova posterior a `20260814_11`.

### Testes

- unitários do domínio `claims`;
- unitários de comandos, serviço, autorização, audit e portas;
- fixture sintética F5.2 determinística e rastreável, em caminho de testes
  definido durante a implementação sem reutilizar dados reais;
- fakes transacionais mínimos;
- integração PostgreSQL específica da F5.2;
- migration/metadata;
- testes arquiteturais;
- regressão F5.1.

### Documentação de fechamento

- `AGENTS.md` e `PLANS.md`, somente após autorização apropriada;
- índices `docs/README.md` e `docs/adr/README.md`;
- `docs/evidence-contract.md`;
- `docs/data-model.md`;
- `docs/architecture.md`;
- `docs/security.md`;
- `docs/testing-strategy.md`;
- registro em `docs/validation/` próprio da F5.2.

Não criar arquivos vazios, abstrações sem uso ou pacote de fase posterior.

## Domínio

### Identificadores

Introduzir tipos UUID distintos para:

- `ClaimId`;
- `ClaimCommandId`.

Um ID de Evidence, Investigation ou Company nunca substitui Claim ID por
compatibilidade estrutural.

### Predicates V1

O vocabulário inicial e versionado é:

| Predicate                 | Versão | Valor permitido                    |
| ------------------------- | -----: | ---------------------------------- |
| `LEGAL_NAME`              |      1 | `TextClaimValue`                   |
| `REGISTRATION_STATUS`     |      1 | `RegistrationStatusClaimValue`     |
| `INCORPORATION_DATE`      |      1 | `DateClaimValue`                   |
| `COUNTRY_OF_REGISTRATION` |      1 | `CountryCodeClaimValue`            |
| `REGISTRATION_IDENTIFIER` |      1 | `RegistrationIdentifierClaimValue` |

Regras mínimas:

- texto não vazio, limitado e sem controles;
- status fechado `ACTIVE`, `INACTIVE`, `DISSOLVED`, `UNKNOWN`;
- data civil não aceita datetime;
- país usa `CountryCode` já existente;
- identificador preserva tipo, valor original e jurisdição tipados;
- predicate desconhecido, versão diferente de 1 ou value incompatível falha;
- não existe escape por string genérica, metadata dinâmica ou plugin.

Extensão futura exige versão/vocabulário explícitos e testes, sem mudar a
semântica de registros anteriores.

### Claim

Campos mínimos:

- `id`, `series_id`, `version`, `supersedes_claim_id`;
- `workspace_id`, `investigation_id`, `subject_company_id`;
- `entity_resolution_decision_id`;
- `command_id`, `command_digest`;
- predicate code/version;
- valor tipado;
- temporalidade tipada;
- criticidade;
- método e versão de criação;
- ator e instante;
- motivo de correção quando aplicável;
- schema e digest.

Invariantes:

- primeira versão: `version=1`, `series_id=id`, sem superseded;
- versão posterior: contígua, outro ID e superseded exatamente anterior;
- escopo, Company e decisão não mudam dentro da série;
- workspace, Investigation, Company, decisão, `predicate_code` e
  `predicate_version` são invariantes da série;
- correção pode mudar valor, temporalidade, criticidade, método/versionamento
  quando justificável e links, preservando o motivo fechado;
- predicate diferente exige nova Claim/série e não cria relação com a série
  conceitualmente errada nesta fase;
- UTC e temporalidade coerente;
- tipo do valor compatível com predicate/version;
- digest recalculável sobre representação canônica;
- `repr` não contém valor ou dados empresariais.

### Temporalidade

Definir união fechada para:

- ocorrência pontual;
- intervalo de vigência;
- ausência explicitamente justificada.

Datas civis e instantes UTC permanecem distintos. Início não sucede fim.
Predicates podem restringir a forma temporal, sem inventar datas ausentes.

### Criticidade

Criticidade é enum fechado e apenas metadado. Não altera assessment, não chama
review workflow e não torna Claim factual.

### ClaimEvidenceUseDecision

Campos conceituais:

- outcome `ELIGIBLE`, `RESTRICTED` ou `REJECTED`;
- reason code fechado;
- `policy_id` e `policy_version`;
- finalidade `INTERNAL_CLAIM_VERIFICATION`;
- `controlled_corpus_manifest_version`;
- `controlled_corpus_manifest_digest`;
- `requested_by`;
- `evaluated_at`.

Não usar `ADMISSIBLE` como outcome. Não alterar Evidence. O outcome é produzido
somente pela política determinística; não existe `decided_by`, permissão humana
de decisão ou override na F5.2.

### Manifesto e política controlada V1

O componente futuro
`src/intelligence/application/claim_evidence_policy.py` conterá uma estrutura
Python imutável/versionada para `F5_2_CONTROLLED_CORPUS_MANIFEST_V1` e a política
`F5_2_CONTROLLED_CORPUS_V1`. Ele fica fora de `intelligence.evidence` porque
avalia o uso cross-aggregate de Artifact/Evidence em Claim.

O manifesto:

- contém somente `ControlledEvidenceAnchorV1` sintéticas e conhecidas;
- não é comando, campo de Artifact/Evidence, tabela, SQL ou approval G6;
- não usa rede, fonte externa mutável, filesystem mutável em runtime ou variável
  de ambiente capaz de adicionar confiança;
- é carregado deterministicamente com o código/configuração interna versionada;
- tem ID, version e digest próprios;
- referencia conceitualmente fixtures sintéticas rastreáveis, nunca magic hashes
  sem origem recomputável.

Cada `ControlledEvidenceAnchorV1` contém:

- `artifact_original_sha256`;
- `evidence_content_sha256`;
- `evidence_kind`;
- `locator_type`;
- `locator_digest`.

A identidade é a combinação exata dos cinco campos. IDs variáveis de workspace,
usuário, Artifact, Evidence e Claim não entram na âncora. Nenhum campo da âncora
é aceito do comando como prova de confiança.

`locator_digest` é SHA-256 UTF-8 de
`locator_to_canonical_json(Evidence.locator)`. Essa função F5.1 já inclui o tipo,
todos os campos semanticamente relevantes e hashes/âncoras do locator. Não criar
segunda canonicalização com semântica diferente.

Algoritmo conceitual do digest:

1. converter os três campos SHA-256 para lowercase;
2. validar cada hash/digest com exatamente 64 caracteres hexadecimais;
3. validar `evidence_kind` e `locator_type` contra os enums F5.1;
4. construir a identidade canônica com os cinco campos;
5. falhar se duas entradas normalizadas forem idênticas;
6. ordenar entradas lexicograficamente pela representação canônica;
7. serializar canonicamente manifest ID, version e entradas ordenadas;
8. calcular SHA-256 da forma canônica.

O digest é calculado/verificado internamente e nunca aceito do comando.
Não eliminar duplicidades silenciosamente. Manifesto inválido, duplicado após
normalização ou adulterado falha na construção. Alterar qualquer campo da âncora
altera o manifest digest.

Toda entrada deve partir de fixture sintética determinística e rastreável. O
revisor deve recomputar bytes originais, `artifact_original_sha256`, conteúdo
localizado, `evidence_content_sha256`, locator canônico, `locator_digest` e
manifest digest. Se não houver fixture adequada, criar futuramente uma fixture
mínima explicitamente F5.2; não usar dado real.

`F5_2_CONTROLLED_CORPUS_V1` somente pode produzir `ELIGIBLE` quando:

1. `EvidenceHistory` reconstitui integralmente;
2. Evidence ID/digest correspondem ao link proposto;
3. tenant, Investigation, Company e decisão correspondem;
4. a versão continua válida/latest para assessment corrente;
5. não existe revogação;
6. Artifact correspondente reconstitui integralmente;
7. os cinco campos reconstituídos correspondem simultaneamente a uma âncora;
8. `Artifact.storage_mode == EXCERPT_ONLY`;
9. `Artifact.retention_mode == INDEFINITE`;
10. `Artifact.display_mode == FULL`;
11. `Evidence.content_original` está presente e seu SHA-256 UTF-8 corresponde a
    `Evidence.content_sha256`;
12. policy ID/version/finalidade são exatamente V1.

Artifact sem entrada produz `RESTRICTED / CONTROLLED_CORPUS_NOT_PROVEN`.
Artifact conhecido com conteúdo, kind ou locator divergente produz
`RESTRICTED / CONTROLLED_EVIDENCE_NOT_PROVEN`. Falha de integridade gera erro
fail-closed, não outcome normal. Qualquer storage/retention/display diferente da
combinação V1 ou `content_original` ausente produz `RESTRICTED`. Metadata textual
pode ser checagem adicional, nunca raiz de confiança.

Suporte a `OBJECT`, `REFERENCE_ONLY`, `EPHEMERAL_PROCESSING`, retenção temporal
ou display redigido exige política futura. O manifesto autoriza somente uso
interno da âncora sintética exata; não altera Evidence `PENDING`, não aprova
fonte/G6 e não torna Claim factual ou reportável.

### ClaimEvidenceLink

Campos mínimos:

- Claim ID exato;
- Evidence ID exato;
- Evidence digest observado;
- role fechado;
- decisão contextual completa gerada pela política;
- schema e link digest.

Invariantes:

- links são tuple imutável e ordenados canonicamente para digest;
- Evidence aparece no máximo uma vez por versão da Claim;
- ao menos um link `SUPPORTS` existe;
- Claim e link compartilham o mesmo workspace;
- role não muda o outcome contextual;
- link histórico nunca é atualizado;
- nova versão da Claim traz conjunto completo de links.

### ClaimHistory

Reconstituir todas as versões e links. Validar:

- série contígua e IDs/comandos únicos;
- encadeamento exato de supersession;
- escopo/Company/decisão/predicate code/predicate version constantes;
- pelo menos um SUPPORTS por versão;
- links pertencentes à versão correta;
- ausência de duplicidade;
- digests e timestamps não regressivos.

Qualquer lacuna, linha extra, adulteração ou troca de escopo gera erro de dados
persistidos, nunca ausência ou replay.

### Assessment

Projetar em leitura:

- `INSUFFICIENT`: zero SUPPORTS elegível e válido;
- `SUPPORTED`: ao menos um SUPPORTS elegível e zero CONTRADICTS elegível;
- `CONFLICTED`: ao menos um SUPPORTS e um CONTRADICTS elegíveis.

Contradição elegível sem suporte elegível continua `INSUFFICIENT`, com razão
fechada. Qualificações elegíveis são retornadas separadamente. Assessment não é
persistido nem tem side effect.

Cada link só contribui depois de reler `EvidenceHistory` e comprovar:

- tenant/Investigation/Company/decisão iguais;
- ID/digest exatos;
- versão ainda latest;
- ausência de revogação;
- integridade integral;
- decisão `ELIGIBLE` para a política/finalidade esperada.

## Aplicação

### Comandos

`RegisterClaim` deve receber, sem workspace fornecido pelo cliente:

- Claim command ID;
- Investigation ID;
- predicate/version e valor tipado;
- temporalidade, criticidade e método/versionamento;
- coleção limitada de links propostos contendo somente Evidence ID, digest
  esperado e role.

`CorrectClaim` acrescenta:

- Claim ID da versão atual;
- expected Claim digest;
- correction reason;
- snapshot completo substituto e todos os links.

`CorrectClaim` segue a mesma regra para o conjunto completo substituto. Nenhum
comando aceita `ClaimEvidenceUseDecision` pronta, outcome, reason code, policy
ID/version, manifest ID/version ou manifest digest. Comandos são imutáveis,
limites de quantidade/tamanho são explícitos e `repr` é redigido. Command digest
usa forma canônica e hashes, não conteúdo original.

### Casos de uso

`RegisterClaim`:

1. valida tipo do comando e digest;
2. autoriza owner/admin;
3. adquire command lock;
4. resolve replay/collision;
5. exige Investigation `VERIFYING`, Company e decisão confirmadas;
6. bloqueia Evidence em ordem determinística;
7. relê e valida `EvidenceHistory` e Artifact;
8. aplica `F5_2_CONTROLLED_CORPUS_V1` com o manifesto interno;
9. gera `ClaimEvidenceUseDecision` para cada link;
10. constrói todos os links;
11. constrói e valida ClaimHistory integralmente;
12. chama o adapter somente depois da validação;
13. adiciona auditoria de sucesso;
14. faz commit único.

`CorrectClaim`:

1. segue autorização, idempotência e replay;
2. bloqueia a história da Claim e valida expected digest/latest;
3. exige Investigation ainda `VERIFYING`;
4. rejeita mudança de predicate code/version;
5. bloqueia as Evidence do novo snapshot em ordem;
6. relê Artifact/Evidence e gera decisões pela política;
7. cria nova versão e novos links completos;
8. não altera versão/link anterior;
9. persiste e audita atomicamente.

Leitura:

- owner/admin/analyst/viewer autorizados;
- lookup tenant-first;
- reconstitui ClaimHistory integral;
- aceita `VERIFYING` e estados posteriores compatíveis definidos
  explicitamente;
- calcula assessment corrente relendo as Evidence;
- não grava cache, evento ou estado;
- ausência cross-tenant gera leitura negada sem ID estrangeiro.

### Resultados

Resultados devem conter ClaimHistory, assessment corrente e flag de replay,
sem classificar a Claim como factual, aprovada ou reportável.

### Erros

Prever erros públicos constantes e tipados para:

- contexto inválido;
- Investigation fora de `VERIFYING` na mutação;
- Claim ausente;
- suporte ausente;
- Evidence inelegível/inválida;
- digest/versão obsoletos;
- link duplicado;
- command collision;
- história/digest persistido inválido;
- política de corpus não comprovada;
- mudança de predicate code/version na série.

Não expor valor, predicate, origem, locator, SQL ou ID cross-tenant.

## Autorização

Adicionar permissões internas fechadas equivalentes a:

- Claim read;
- Claim register;
- Claim correct.

Matriz:

| Papel   | Read | Register | Correct |
| ------- | ---: | -------: | ------: |
| OWNER   |  sim |      sim |     sim |
| ADMIN   |  sim |      sim |     sim |
| ANALYST |  sim |      não |     não |
| VIEWER  |  sim |      não |     não |

Não criar reviewer e não permitir proposal por analyst. `OWNER` e `ADMIN`
escolhem Evidence e role, mas não podem forçar `ELIGIBLE`, `RESTRICTED` ou
`REJECTED`. Não existe permissão `decide eligibility`.

## Auditoria

Ações mínimas:

- Claim registrada;
- Claim corrigida;
- leitura de Claim negada.

Reason codes mínimos:

- contexto/lifecycle inválido;
- suporte ausente;
- Evidence inelegível;
- corpus controlado não comprovado;
- versão obsoleta;
- link duplicado;
- command collision;
- resource not found e permission denied já existentes quando aplicáveis.

Usar `INVESTIGATION` como tipo de recurso, evitando ampliar o schema de audit.
Não registrar ClaimValue, predicate, temporalidade, Evidence ID cross-tenant,
conteúdo, locator, origem ou digests.

Sucesso compartilha commit com Claim/links. Negação/falha conhecida segue
auditoria standalone sem substituir o erro original se a auditoria falhar.

## Concorrência

### Ordem obrigatória

1. command lock tenant-scoped da Claim;
2. Claim history lock em `CorrectClaim`;
3. Evidence history locks ordenados pelo valor canônico de Evidence ID;
4. releitura integral de Claim/Evidence;
5. validação e construção integral;
6. append de Claim e links;
7. audit append;
8. commit.

Não gerar IDs persistíveis nem chamar adapter antes dos prechecks que puderem
falhar sem necessidade.

### Corridas obrigatórias

- dois `RegisterClaim` com mesmo command ID e mesmo digest;
- mesmo command ID com digest divergente;
- duas correções da mesma Claim/version;
- `RegisterClaim` contra correção da Evidence vinculada;
- `RegisterClaim` contra revogação da Evidence vinculada;
- `CorrectClaim` contra correção/revogação de Evidence;
- operações com as mesmas Evidence em ordens de entrada diferentes.

Resultados permitidos devem ser determinísticos: replay idêntico ou exatamente
uma mutação válida; a operação concorrente relê e falha por versão/eligibilidade
quando necessário. Nunca persistir Claim apoiada por Evidence que mudou durante
a transação.

## Persistência

### Porta ClaimRepository

Superfície append-only:

- `acquire_command_lock`;
- `acquire_history_lock`;
- `add_initial`;
- `add_correction`;
- `get_history`;
- `get_history_by_command`.

Proibir update/delete/save/replace e commit no repositório.

### Tabela claim

Planejar:

- PK de Claim ID;
- chaves de escopo e decisão;
- command ID/digest;
- series/version/superseded;
- predicate/version;
- value type/snapshot schema fechado;
- temporalidade e criticidade;
- método/versionamento;
- correction reason;
- ator/instante;
- schema/digest;
- UNIQUE tenant-scoped de command ID;
- UNIQUE tenant-scoped de série/versão;
- checks de primeira/correção, predicate/value, temporalidade, digest e schema;
- FKs `RESTRICT` compostas.

### Tabela claim_evidence_link

Planejar:

- Claim e Evidence IDs;
- workspace, Investigation, Company e decisão;
- Evidence digest observado;
- role;
- outcome/razão/política/finalidade da decisão;
- manifest version/digest;
- requested by/evaluated at;
- schema/link digest;
- unicidade Claim/Evidence;
- FKs compostas para os dois lados;
- checks de enums, política V1, finalidade, digests e schema;
- índices tenant-first por Claim e por Evidence.

O link não duplica os cinco campos da âncora. Evidence ID/digest, policy
ID/version, manifest version/digest, outcome/reason e requested by/evaluated at
são suficientes porque Evidence/Artifact históricos preservam os demais valores
reconstituídos usados pela política.

A exigência “ao menos um SUPPORTS” é invariante do agregado e da
reconstituição; não introduzir trigger sem decisão específica.

## Migration futura

- criar revision posterior a `20260814_11` somente após autorização;
- nunca editar `20260814_11_add_canonical_evidence_core.py`;
- preservar as 22 tabelas e dados atuais;
- criar somente `claim` e `claim_evidence_link`;
- adicionar à Evidence apenas a chave candidata composta estritamente necessária
  para FK de tenant/Investigation/Company/decisão;
- usar `RESTRICT`, sem cascade destrutiva;
- adicionar índices motivados pelos casos de uso;
- downgrade pode remover estrutura vazia, mas deve recusar perda de histórico
  quando houver Claim/link;
- testar upgrade a partir de base e head anterior, metadata convergence,
  downgrade/re-upgrade e dados F5.1 preservados.

## Segurança

- nenhuma fonte real, rede, filesystem, upload ou I/O externo;
- tratar ClaimValue e Evidence como dados não confiáveis;
- limites explícitos de links, texto, snapshot e reason codes;
- códigos/predicates/enums fechados;
- validação tenant-first na aplicação e no banco;
- nenhum valor/conteúdo em repr, logs, erro ou audit;
- SQLAlchemy somente com binds/metadata, nunca SQL construído de entrada;
- reconstituição recalcula digests e falha fechado;
- source snapshots não provam autorização;
- hash isolado de Artifact não prova Evidence controlada;
- somente match simultâneo dos cinco campos de `ControlledEvidenceAnchorV1` pode
  provar a âncora sintética;
- toda âncora deriva de fixture sintética rastreável e recomputável;
- magic hash e dados reais são proibidos;
- comandos/atores não controlam outcome ou manifest digest;
- manifesto não depende de SQL, rede, runtime filesystem ou environment;
- a canonicalização do locator reutiliza `locator_to_canonical_json` da F5.1;
- divergência de âncora gera restrição; falha de integridade gera erro;
- sem confiança agregada, inferência, prioridade de fonte ou escolha de verdade;
- nenhuma dependência nova.

## Testes obrigatórios

### Domínio

- cada predicate V1 com seu ClaimValue correto;
- toda combinação predicate/value incorreta;
- limites, controles, UTC, datas e temporalidade;
- primeira versão e cadeia de correções;
- scope/custody imutáveis;
- digest e redaction;
- ao menos um SUPPORTS;
- roles/outcomes fechados;
- Evidence duplicada no link;
- ClaimHistory válida e adulterações;
- assessment em todas as combinações relevantes;
- contradição sem suporte → `INSUFFICIENT` com reason code;
- RESTRICTED/REJECTED nunca contam.

### Política V1

- escopo, history, ID, digest, latest e revogação;
- Artifact conhecido + Evidence controlada exata → pode prosseguir para
  `ELIGIBLE`;
- Artifact conhecido + `content_sha256` diferente → `RESTRICTED`;
- Artifact conhecido + conteúdo conhecido + locator diferente → `RESTRICTED`;
- Artifact conhecido + locator conhecido + conteúdo diferente → `RESTRICTED`;
- Artifact desconhecido → `CONTROLLED_CORPUS_NOT_PROVEN`;
- locator digest adulterado → falha ou restrição conforme a origem da
  divergência;
- mudança de um campo do locator altera locator digest;
- duas entradas idênticas no manifesto → manifesto inválido;
- hashes com caixa diferente que normalizam para duplicata → manifesto inválido;
- cada entrada é recomputável de fixture sintética rastreada;
- nenhum magic hash sem fixture correspondente;
- `source_id` falsificado não produz `ELIGIBLE`;
- `origin_type` falsificado não produz `ELIGIBLE`;
- `source_id` ou `origin_type` falsificado não substitui match da âncora;
- storage diferente de `EXCERPT_ONLY` → `RESTRICTED` na V1;
- retention diferente de `INDEFINITE` → `RESTRICTED` na V1;
- display diferente de `FULL` → `RESTRICTED` na V1;
- `content_original=None` → `RESTRICTED` na V1;
- `content_original` cujo hash diverge de `content_sha256` → erro de integridade;
- manifest digest adulterado falha;
- outcome da política é determinístico;
- finalidade diferente falha fechado;
- política/versão desconhecida falha;
- Evidence global continua `PENDING`.

### Aplicação

- matriz exaustiva dos quatro papéis;
- tipo do comando torna impossível fornecer outcome;
- OWNER não consegue forçar `ELIGIBLE`;
- ADMIN não consegue forçar `ELIGIBLE`;
- mutação somente em `VERIFYING`;
- `COLLECTING` sempre rejeitado;
- leitura em estados explicitamente compatíveis;
- replay/collision e expected digest;
- escopo/Company/decisão de todas as Evidence;
- validação completa antes do adapter;
- auditoria de sucesso/negação/falha;
- erros e repr redigidos.

### Correção de Claim

- predicate diferente em correção é rejeitado;
- predicate version diferente em correção é rejeitado;
- value diferente e compatível com o mesmo predicate é permitido;
- adulteração de predicate/version na história falha fechado;

### Persistência PostgreSQL

- round-trip completo e ordenado;
- filtros tenant-first;
- FKs cross-tenant/cross-Investigation/cross-Company/cross-decision;
- versão, supersession e command uniqueness;
- link duplicado;
- mappers rejeitam schema/enums/digest/value adulterados;
- história incompleta ou linha extra falha fechado;
- rollback sem Claim/link/audit parcial;
- guard impede autobegin/reuso após finalização.

### Concorrência

- matriz de corridas definida na seção própria;
- barreiras/eventos, lock timeout local e joins limitados;
- sem sleep arbitrário como sincronização;
- repetir cenários sensíveis conforme padrão vigente.

### Migration

- revision anterior e banco vazio;
- constraint/index/FK names estáveis;
- `alembic check`;
- downgrade protegido;
- F5.1 preservada.

### Arquitetura

- `intelligence.claims` sem infraestrutura, framework, rede, filesystem, relógio
  ou aleatoriedade;
- `intelligence.evidence` não importa `claims`;
- `claims` não importa connectors, risk, reporting, interfaces ou orchestration;
- repositórios sem commit/rollback/conexão própria;
- exatamente duas tabelas e uma migration nova;
- ausência de HTTP, jobs, IA, risco, relatório e F5.3.

### Regressão F5.1

- toda a suíte F5.1 passa sem relaxamento;
- Evidence continua `PENDING` no domínio e banco;
- hashes, locators, correção/revogação e policy modes permanecem inalterados;
- migration 11 conserva hash/conteúdo e não é reescrita;
- concorrência Evidence×Evidence continua válida.

## Cobertura

- `intelligence.claims`: pelo menos 90% de branch coverage;
- invariantes críticas e outcomes: 100% exercitados;
- cobertura global: pelo menos 80% de linhas;
- nenhuma linha irrelevante para elevar cobertura;
- sem skip de teste crítico sem aceite explícito.

## Validações e gates

Quando a implementação estiver autorizada, executar e registrar:

1. lint Python/web e scanner de segredos;
2. formatação Python/Prettier;
3. mypy estrito e TypeScript;
4. testes focais de claims/evidence;
5. integração PostgreSQL real controlada;
6. migration upgrade/check/downgrade protegido;
7. suíte integral Python e web;
8. builds Python/web;
9. `git diff --check`;
10. revisão de arquitetura e segurança;
11. pacote limpo somente de arquivos rastreados;
12. revisão independente binária.

Falhas, warnings e incidentes intermediários devem ser registrados sem
conversão artificial em sucesso.

## Documentação

No mesmo conjunto futuro de implementação:

- manter ADR 0025 `Proposed` até revisão independente final;
- documentar a solução aprovada para prova de corpus;
- atualizar contrato e data model sem redefinir admissibilidade global;
- registrar que assessment é somente corrente;
- registrar a ausência de runtime path até `VERIFYING`;
- manter Gate E2E aberto e F5.3 não autorizada;
- criar validação F5.2 com comandos/resultados reais.

## Critérios de aceite da implementação

1. Claim imutável/versionada e links exatos funcionam por portas e PostgreSQL.
2. Somente owner/admin registram/corrigem; analyst/viewer somente leem.
3. Registro/correção em `COLLECTING` é sempre rejeitado.
4. Evidence permanece globalmente `PENDING`.
5. `ClaimEvidenceUseDecision` nunca usa `ADMISSIBLE`.
6. Apenas `ELIGIBLE` contribui para assessment.
7. Claim exige SUPPORTS, mas pode resultar `INSUFFICIENT`.
8. Assessment não é persistido e reage a correction/revocation de Evidence.
9. IDs/digests/escopo exatos são revalidados em toda leitura.
10. Claim, links e auditoria são atômicos.
11. Concorrência não cria suporte sobre Evidence que mudou.
12. Duas tabelas append-only, migration nova e FKs tenant-scoped.
13. Política usa manifesto interno imutável de `ControlledEvidenceAnchorV1`,
    digest verificado e não representa G6.
14. Testes, tipos, lint, scanner, builds, coverage e regressão F5.1 passam.
15. Documentação permanece consistente e nenhuma capacidade posterior aparece.
16. Revisão independente emite parecer de aceite.
17. Outcome é sempre gerado pela política e nunca fornecido por comando/ator.
18. Correção preserva predicate code/version da série.
19. `ELIGIBLE` exige match simultâneo de Artifact hash, Evidence content hash,
    Evidence kind, locator type e locator digest.
20. Cada âncora e o manifesto completo são recomputáveis de fixtures sintéticas
    rastreadas.
21. Policy V1 aceita somente `EXCERPT_ONLY`, `INDEFINITE`, `FULL` e
    `content_original` íntegro.
22. Duplicata normalizada invalida o manifesto sem deduplicação silenciosa.

## Critérios de bloqueio

Bloquear implementação ou fechamento se ocorrer qualquer item:

- manifesto contém hash não sintético ou não aprovado para teste interno;
- âncora não corresponde a fixture sintética rastreável/recomputável;
- manifesto/digest pode ser alterado por comando, SQL, filesystem runtime ou
  variável de ambiente;
- F5.2 é bloqueada se `ELIGIBLE` puder ser obtido somente pela presença do
  Artifact hash, sem match exato da âncora de Evidence controlada;
- canonicalização de locator diverge de `locator_to_canonical_json` da F5.1;
- duplicatas normalizadas são eliminadas em vez de invalidar o manifesto;
- policy V1 aceita storage, retention ou display fora da combinação conservadora
  sem nova versão;
- `ELIGIBLE` depende de texto/prefixo/origin type controlado pelo envelope;
- comando aceita outcome, reason, policy ou manifest digest pronto;
- OWNER/ADMIN consegue forçar outcome;
- correção altera predicate code/version da série;
- alteração de Evidence/admissibility/lifecycle F5.1;
- Claim permitida em `COLLECTING`;
- ANALYST ganha mutação ou decisão;
- assessment/status persistido;
- link aponta para latest implícito;
- update/delete de Claim/link;
- terceira tabela de lifecycle sem nova decisão;
- cross-tenant possível no serviço ou schema;
- ausência de lock/revalidação Claim×Evidence;
- migration 11 reescrita ou dados existentes perdidos;
- teste crítico falho/skipped, type error, segredo ou migration divergente;
- introdução de HTTP, fonte real, IA, risco, relatório, jobs ou F5.3;
- ADR 0025 marcado `Accepted` antes do gate independente.

## Instruções para revisão independente

O pacote candidato deverá ser revisado sem assumir que os testes existentes são
suficientes. O revisor deve:

1. confirmar baseline, commits, tag candidata e working tree limpa;
2. inventariar exatamente o diff F5.2;
3. recomputar cada âncora a partir de fixture sintética rastreada e reproduzir o
   manifest digest completo;
4. provar que somente o match simultâneo dos cinco campos da âncora pode
   prosseguir para `ELIGIBLE`, sem aprovação inventada;
5. revisar domínio, application boundaries, portas, UoW e migration;
6. verificar predicates/value mappings, invariância da série e ausência de
   vocabulário subjetivo;
7. confirmar que locator digest reutiliza a canonicalização F5.1 e muda com
   qualquer campo semanticamente relevante;
8. provar rejeição de duplicatas normalizadas e de magic hashes;
9. reproduzir tenancy e adulteração em PostgreSQL;
10. reproduzir corridas Claim×Evidence;
11. confirmar que Evidence permanece `PENDING`;
12. confirmar que assessment não é persistido;
13. executar gates focais e integrais;
14. revisar segurança, redaction e ausência de escopo posterior;
15. classificar o gate como `APPROVED`, `APPROVED_WITH_FIXES` ou `BLOCKED`.

## Fechamento independente

Parecer: `APPROVED_WITH_FIXES`.

Foram corrigidos snapshots JSON permissivos, leitura histórica ausente em
`FAILED`/`CANCELLED`, vínculo incompleto da proveniência da decisão e leitura de
assessment sem aquisição prévia de todos os locks de Evidence. Testes unitários,
PostgreSQL, regressão F5.1, migrations, segurança, cobertura e quality gate
passaram. O ADR 0025 foi aceito e o checkpoint final pode ser criado; a revisão
não autoriza F5.3.
