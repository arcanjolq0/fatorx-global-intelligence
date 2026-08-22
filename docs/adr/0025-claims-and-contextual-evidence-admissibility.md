# ADR 0025 — Claims e elegibilidade contextual de evidência

- Status: Accepted
- Data: 2026-08-21
- Data de aceite: 2026-08-22
- Decisores: responsável pelo projeto e revisão independente da F5.2
- Relacionados: ADR 0003, ADR 0007, ADR 0008, ADR 0011, ADR 0013, ADR 0023 e ADR 0024

## Contexto

A F5.1 materializou `Artifact`, versões imutáveis de `Evidence` e
`EvidenceLifecycleEvent`. Cada Evidence está ligada a uma Investigation, uma
Company confirmada, uma decisão humana de resolução de entidade e um Artifact
do mesmo workspace. A história é reconstituída integralmente, digests e locators
são verificados e correções/revogações são append-only.

O ADR 0024 determina que toda Evidence F5.1 nasce e permanece com
`Evidence.admissibility_status = PENDING`. O banco repete essa regra por
constraint. O vocabulário `PENDING`, `ADMISSIBLE`, `RESTRICTED`, `EXPIRED`,
`REVOKED` e `REJECTED` pertence à admissibilidade global da própria Evidence e
não pode ser reutilizado com outro significado.

O ADR 0003 exige separar `Artifact`, `Evidence`, `Claim` e
`ClaimEvidenceLink`. O contrato de evidências exige links explícitos de suporte,
contradição ou qualificação. A implementação materializa essa fronteira e foi
aceita após revisão independente com correções em 2026-08-22.

A autorização de 2026-08-21 permitiu implementar somente a F5.2 como candidata,
sem promover este ADR naquele checkpoint. O gate independente posterior aceitou
o código, a migration e os testes; mudança do lifecycle, F5.3 e capacidades
posteriores continuam não autorizadas.

## Problema

A próxima fronteira factual precisa registrar uma afirmação estruturada e a
relação rastreável com versões exatas de Evidence, sem:

- alterar a custódia ou a admissibilidade global da Evidence;
- tratar Claim como verdade, fato reportável, inferência ou risco;
- aceitar referência cross-tenant ou a uma versão implícita `latest`;
- descartar contradições, links restritos ou links rejeitados;
- persistir um assessment que fique obsoleto após correção ou revogação;
- inventar que uma fonte, política ou corpus está aprovado;
- antecipar review workflow, relatório, HTTP, jobs ou lifecycle.

`Artifact` e `Evidence` não contêm um marcador confiável de corpus controlado.
`source_id`, `source_policy_version`, `origin_reference` e
`acquisition_method` são snapshots textuais obrigatórios, mas não possuem FK
para catálogo aprovado. `origin_type` distingue `CONNECTOR`, `USER_UPLOAD`,
`FILE_IMPORT` e `MANUAL_REFERENCE`; nenhum valor comprova que o material é
sintético ou autorizado. Fingerprints, hashes, storage, retenção, exibição e
sensibilidade provam outras propriedades, não a autorização do corpus.

O identificador documental `source.synthetic.business_registry` pertence à
fixture operacional F4.6 e não representa `APPROVED_TEST`. Usar seu nome ou um
prefixo como prova seria confiar em texto fornecido ao envelope e inventar
aprovação de fonte. A F5.2 precisa, portanto, de uma raiz de confiança interna e
versionada que reconheça bytes sintéticos exatos sem alterar a F5.1 ou simular
aprovação G6.

O hash do Artifact isolado também não basta. A F5.1 calcula
`Artifact.original_content_sha256` sobre os bytes originais e
`Evidence.content_sha256` sobre o conteúdo localizado; essas entradas são
distintas. Um Artifact conhecido não prova que uma Evidence específica, seu
conteúdo localizado e seu locator pertencem ao corpus controlado.

## Decisão

### 1. Fronteira da F5.2

A F5.2 proposta materializa somente:

1. Claim imutável, tenant-scoped e versionada;
2. `ClaimEvidenceLink` imutável entre versões exatas;
3. `ClaimEvidenceUseDecision` embutida no link;
4. assessment corrente derivado e fail-closed;
5. casos de uso internos de registro, correção, leitura e assessment;
6. persistência append-only futura em duas tabelas.

Não existe transição de Investigation, Evidence ou Claim nesta unidade. Uma
correção é outra versão completa, não alteração de estado.

### 2. Admissibilidade global versus elegibilidade contextual

`Evidence.admissibility_status` permanece `PENDING`. A F5.2 não altera a linha,
o enum, o digest, o mapper, a constraint ou o lifecycle da Evidence.

Cada `ClaimEvidenceLink` contém uma `ClaimEvidenceUseDecision` distinta, com
outcomes fechados:

- `ELIGIBLE`;
- `RESTRICTED`;
- `REJECTED`.

A pergunta respondida é somente:

> Esta versão exata da Evidence pode participar da avaliação desta versão exata
> da Claim para esta finalidade interna e esta política?

A decisão registra conceitualmente:

- `outcome`;
- `reason_code`;
- `policy_id`;
- `policy_version`;
- finalidade;
- `controlled_corpus_manifest_version`;
- `controlled_corpus_manifest_digest`;
- `requested_by`;
- `evaluated_at`.

`requested_by` identifica o ator que solicitou o registro/correção e selecionou
Evidence/role; não o transforma em decisor do outcome. Não existe default.
Somente `ELIGIBLE` contribui para o assessment. `RESTRICTED` e `REJECTED`
permanecem no histórico, mas não contam como suporte, contradição ou
qualificação efetiva na F5.2.

O outcome é derivado exclusivamente pela política determinística. `OWNER` e
`ADMIN` selecionam Evidence e atribuem `SUPPORTS`, `CONTRADICTS` ou `QUALIFIES`,
mas não fornecem nem sobrescrevem outcome, razão, política ou digest do
manifesto. O serviço cria `ClaimEvidenceUseDecision` depois de reler e validar
Evidence/Artifact e executar a política. Override humano futuro exigirá uma
`ReviewDecision` append-only separada e não pertence à F5.2.

`ClaimEvidenceUseDecision` não:

- promove a Evidence para `ADMISSIBLE`;
- satisfaz o Gate G6;
- aprova ou ativa fonte real;
- transforma Claim em fato, verdade ou dado reportável;
- autoriza relatório, exportação ou redistribuição;
- substitui admissibilidade global ou revisão humana futura.

### 3. Manifesto controlado e política V1

A raiz de confiança proposta é o manifesto interno imutável e versionado
`F5_2_CONTROLLED_CORPUS_MANIFEST_V1`. Sua unidade de confiança é
`ControlledEvidenceAnchorV1`, uma âncora sintética completa com:

- `artifact_original_sha256`;
- `evidence_content_sha256`;
- `evidence_kind`;
- `locator_type`;
- `locator_digest`.

A identidade de uma entrada é a combinação exata dos cinco campos. O hash do
Artifact sozinho nunca comprova Evidence controlada. IDs de workspace, usuário,
Artifact, Evidence ou Claim não fazem parte da âncora porque variam entre
execuções.

O manifesto pertence ao código/configuração interna versionada do sistema. Na
organização atual, o componente fica em
`src/intelligence/application/claim_evidence_policy.py`, junto à política
cross-aggregate da F5.2 e fora de `intelligence.evidence`. Ele é uma estrutura
Python imutável, carregada deterministicamente, sem SQL, rede, leitura de
filesystem mutável em runtime ou variável de ambiente capaz de confiar em hash
arbitrário. Não é parâmetro de comando, campo de Artifact/Evidence, texto do
usuário, `source_id`, prefixo de origem nem aprovação G6.

`locator_digest` é o SHA-256 UTF-8 de
`locator_to_canonical_json(Evidence.locator)`, representação canônica já usada
pela F5.1. Ela inclui `locator.type`, todos os campos semanticamente relevantes
e os hashes/âncoras próprios de cada locator. A F5.2 não cria outra
canonicalização para o mesmo locator; qualquer evolução incompatível exige nova
versão da política/manifesto.

Cada entrada precisa corresponder a fixture sintética determinística e
rastreável no repositório. O revisor deve conseguir recomputar bytes originais,
hash do Artifact, conteúdo localizado, hash da Evidence, locator canônico,
`locator_digest` e digest do manifesto. Magic hash sem fixture correspondente e
dados reais são proibidos. Se as fixtures existentes não forem adequadas, a
implementação futura pode adicionar fixture sintética mínima identificada para
F5.2; isso não cria fonte real nem satisfaz G6.

O manifesto e seu digest são construídos deterministicamente:

1. normalizar os três campos SHA-256 de cada âncora para lowercase;
2. exigir exatamente 64 caracteres hexadecimais em cada hash/digest;
3. validar `evidence_kind` e `locator_type` nos enums F5.1;
4. construir a representação canônica com os cinco campos;
5. falhar se duas entradas normalizadas forem idênticas;
6. ordenar as entradas lexicograficamente pela representação canônica;
7. serializar canonicamente manifest ID, manifest version e entradas ordenadas;
8. calcular SHA-256 da forma canônica.

Não existe deduplicação silenciosa. Alterar conteúdo localizado, kind, locator
type ou locator digest altera o digest do manifesto. Manifesto inválido,
duplicado ou com digest interno divergente falha fechado. O comando não fornece
âncora, manifest ID, version, conteúdo ou digest.

A política proposta é:

- identificador: `F5_2_CONTROLLED_CORPUS_V1`;
- versão: `1`;
- finalidade única: `INTERNAL_CLAIM_VERIFICATION`.

Ela somente pode emitir `ELIGIBLE` quando, em conjunto:

1. `EvidenceHistory` reconstitui integralmente;
2. Evidence vinculada corresponde ao ID e digest esperados;
3. Evidence pertence ao mesmo workspace, Investigation, Company e decisão;
4. a versão vinculada continua válida para assessment corrente e não foi
   superseded;
5. Evidence não está revogada;
6. Artifact correspondente reconstitui integralmente;
7. existe uma única `ControlledEvidenceAnchorV1` que corresponde simultaneamente
   a `Artifact.original_content_sha256`, `Evidence.content_sha256`,
   `Evidence.kind`, `Evidence.locator.type` e ao digest canônico do locator;
8. `Artifact.storage_mode == EXCERPT_ONLY`;
9. `Artifact.retention_mode == INDEFINITE`;
10. `Artifact.display_mode == FULL`;
11. `Evidence.content_original` está presente e seu SHA-256 UTF-8 corresponde a
    `Evidence.content_sha256`;
12. policy ID/version e finalidade são exatamente os esperados.

Artifact sem nenhuma entrada correspondente produz
`RESTRICTED / CONTROLLED_CORPUS_NOT_PROVEN`. Artifact conhecido com
`content_sha256`, kind, locator type ou locator digest divergente produz
`RESTRICTED / CONTROLLED_EVIDENCE_NOT_PROVEN`. Falha de integridade gera erro
fail-closed apropriado, não outcome normal. Restrição explícita de uso produz
`RESTRICTED` ou `REJECTED`, conforme razão fechada.

Qualquer storage diferente de `EXCERPT_ONLY`, retention diferente de
`INDEFINITE`, display diferente de `FULL` ou `content_original` ausente produz
`RESTRICTED` na V1. Suporte a `OBJECT`, `REFERENCE_ONLY`,
`EPHEMERAL_PROCESSING`, retenção temporal ou exibição redigida fica para versão
futura da política. Esta restrição é deliberadamente conservadora e exclusiva
do corpus sintético interno F5.2.

`source_id`, nome de fixture, `origin_type`, prefixo, filename e
`acquisition_method` podem ser conferidos como consistência adicional, mas nunca
substituem o match exato da âncora.

A entrada no manifesto autoriza somente o uso da combinação sintética exata de
Artifact, conteúdo localizado e locator em `INTERNAL_CLAIM_VERIFICATION`. Ela
não prova autenticidade externa, não aprova fonte real, não satisfaz G6, não
torna Evidence `ADMISSIBLE` e não torna Claim factual ou reportável. O manifesto,
a política e sua recomputação independente foram aprovados no gate final F5.2.

### 4. Modelo de Claim

`Claim` é uma afirmação estruturada sobre a Company confirmada de uma
Investigation. Ela é imutável, append-only e possui:

- Claim ID;
- series ID;
- versão positiva e contígua;
- Claim ID superseded, ausente somente na primeira versão;
- workspace;
- Investigation;
- Company;
- decisão de resolução de entidade;
- predicate code e versão;
- valor tipado;
- temporalidade tipada;
- criticidade;
- método e versão de criação;
- ator e instante;
- schema e digest;
- motivo fechado de correção nas versões posteriores.

A primeira versão inicia sua própria série. Cada correção cria nova Claim,
aponta exatamente para a versão anterior e fornece um conjunto completo e novo
de links. Workspace, Investigation, Company, decisão de resolução de entidade,
`predicate_code` e `predicate_version` são invariantes da série. Uma correção
pode mudar valor, temporalidade, criticidade, método/versionamento quando
justificável e links, mas nunca o predicate. Predicate conceitualmente errado
exige nova Claim/série; a F5.2 não relaciona nem retrata a série anterior. Claim
e links históricos nunca são alterados.

A F5.2 não cria status persistido da Claim. Em particular, não existem:
`TRUE`, `FALSE`, `FACTUAL`, `APPROVED`, `REPORTABLE`, `REFUTED`, `SCORED` ou
qualquer estado de risco.

### 5. Predicates e valores V1

O catálogo fechado inicial contém somente predicates estruturais:

| Predicate                 | Versão | Tipo de `ClaimValue`                                      |
| ------------------------- | -----: | --------------------------------------------------------- |
| `LEGAL_NAME`              |      1 | texto não vazio e limitado                                |
| `REGISTRATION_STATUS`     |      1 | enum fechado `ACTIVE`, `INACTIVE`, `DISSOLVED`, `UNKNOWN` |
| `INCORPORATION_DATE`      |      1 | data civil, nunca datetime                                |
| `COUNTRY_OF_REGISTRATION` |      1 | `CountryCode` ISO 3166-1 alfa-2-shaped                    |
| `REGISTRATION_IDENTIFIER` |      1 | tipo, valor original e jurisdição tipados                 |

O mapeamento predicate→tipo é determinístico e validado no domínio. Um
`predicate_code` desconhecido ou uma versão não suportada falha fechado. A
persistência poderá usar `value_type` e snapshot canônico versionado, mas JSONB
não substituirá a união tipada do domínio.

Não pertencem à V1 predicates de risco, score, fraude, sanção, litígio,
reputação, crédito, recomendação ou classificação subjetiva.

### 6. Temporalidade e criticidade

A temporalidade deve distinguir, por tipo fechado, ocorrência pontual, período
de vigência e ausência explicitamente justificada. Instantes são UTC; datas
civis não são convertidas silenciosamente em datetime. Início não pode suceder
fim. O predicate limita as formas temporais aceitas quando necessário.

A criticidade é metadado fechado da Claim. Ela não concede factualidade nem
altera o assessment. Gates de claim crítica, revisão e relatório permanecem
posteriores.

### 7. ClaimEvidenceLink

A relação é muitos-para-muitos. Cada link aponta para:

- Claim ID e versão exatos;
- Evidence ID exato;
- digest exato da Evidence observado;
- role;
- `ClaimEvidenceUseDecision`;
- política e versão da decisão;
- finalidade;
- versão e digest do manifesto controlado;
- `requested_by` e `evaluated_at`;
- schema e digest do link.

Roles fechados:

- `SUPPORTS`: conteúdo compatível com a afirmação;
- `CONTRADICTS`: conteúdo incompatível;
- `QUALIFIES`: limita escopo, tempo ou interpretação.

Uma versão de Evidence aparece no máximo uma vez em uma versão de Claim. O link
nunca aponta implicitamente para `latest`. Uma Claim registrada exige ao menos
um link `SUPPORTS`, ainda que a decisão contextual desse link seja `RESTRICTED`
ou `REJECTED`. Assim, uma Claim pode resultar `INSUFFICIENT`, mas nunca existe
sem tentativa explícita e rastreável de suporte.

### 8. Assessment corrente

O assessment é uma projeção de leitura. Ele nunca é coluna, snapshot, cache ou
evento persistido na F5.2.

Outcomes fechados:

- `INSUFFICIENT`: nenhum `SUPPORTS + ELIGIBLE` continua válido;
- `SUPPORTED`: existe `SUPPORTS + ELIGIBLE` válido e não existe
  `CONTRADICTS + ELIGIBLE` válido;
- `CONFLICTED`: existem simultaneamente `SUPPORTS + ELIGIBLE` e
  `CONTRADICTS + ELIGIBLE` válidos.

Se houver apenas contradição elegível e nenhum suporte elegível, o resultado é
`INSUFFICIENT`, com razão fechada que pode indicar contradição presente. Não há
`FALSE`, `REFUTED` ou `DISPROVED`.

`QUALIFIES + ELIGIBLE` é devolvido como qualificação rastreável, mas não cria
suporte. `RESTRICTED` e `REJECTED` nunca contribuem nesta unidade.

Para contribuir, a Evidence deve:

- pertencer ao mesmo workspace;
- pertencer à mesma Investigation;
- referir-se à mesma Company e decisão;
- reconstituir sua história integralmente;
- corresponder ao ID e digest gravados no link;
- continuar como a última versão da série para avaliação corrente;
- não estar revogada;
- possuir decisão contextual `ELIGIBLE` válida para política/finalidade.

Qualquer ausência, adulteração ou divergência falha fechado. A leitura não muda
Evidence nem Claim.

### 9. Lifecycle

`RegisterClaim` e `CorrectClaim` exigem Investigation em `VERIFYING`.
`CorrectClaim` mantém essa exigência nesta primeira unidade. Leitura pode
aceitar `VERIFYING` e estados posteriores compatíveis, sem restaurar estado
histórico ou executar transição.

A F5.2 não implementa `NORMALIZING -> VERIFYING` nem qualquer outra transição.
Consequentemente, o caso de uso pode permanecer inalcançável pelo fluxo runtime
atual, que materializa somente até `COLLECTING`. Testes futuros podem
reconstituir snapshots válidos em `VERIFYING`; isso não autoriza exceção para
registrar Claim em `COLLECTING`.

### 10. Autorização

Sem criar papel `REVIEWER` ou workflow de proposta:

| Papel     | Ler | Registrar | Corrigir |
| --------- | --: | --------: | -------: |
| `OWNER`   | sim |       sim |      sim |
| `ADMIN`   | sim |       sim |      sim |
| `ANALYST` | sim |       não |      não |
| `VIEWER`  | sim |       não |      não |

O workspace efetivo vem exclusivamente do `ActorContext`. IDs de outro tenant
aparecem como ausentes. Não existe `workspace_id` fornecido pelo comando.
Também não existe permissão `decide eligibility`: a política, não o ator,
determina o outcome.

### 11. Portas e serviços internos

A porta `ClaimRepository` oferece somente:

- lock tenant-scoped de command ID;
- lock da história da Claim;
- append da primeira Claim e links;
- append de correção e novo conjunto de links;
- leitura integral por Claim ID;
- leitura integral por command ID.

Não existem `update`, `delete`, `save`, `replace` ou listagem irrestrita.

O serviço interno deve autorizar, bloquear, reler e validar todos os agregados,
executar a política com o manifesto interno, gerar cada decisão contextual,
construir `ClaimHistory` e links completos antes do primeiro append e coordenar
Claim, links e auditoria em uma única Unit of Work. Comandos fornecem somente
Evidence ID, digest esperado e role por link; decisões prontas são inválidas por
construção.

Não existe HTTP ou interface pública nesta decisão.

### 12. Persistência proposta

Somente duas tabelas:

1. `claim`;
2. `claim_evidence_link`.

`claim` preserva identidade/versionamento, escopo, predicate/value,
temporalidade, criticidade, método, ator, correção, schema e digest. Deve possuir
unicidade tenant-scoped de command ID e de `(series_id, version)`, além de FKs
compostas para workspace, Investigation, Company, decisão, raiz da série e
versão superseded.

`claim_evidence_link` preserva escopo repetido, Claim/Evidence exatas, role,
digest observado, outcome/reason code derivados, política/finalidade, versão e
digest do manifesto, `requested_by`, `evaluated_at`, schema e digest. A chave
deve impedir que a mesma Evidence apareça duas vezes na mesma versão da Claim.
FKs compostas devem comprovar tenant, Investigation, Company e decisão dos dois
lados.

O manifesto não cria tabela e não é armazenado em tabela F5.1. O link preserva
somente o snapshot de manifest version/digest necessário para reproduzir a
decisão com a versão correspondente do código/configuração interna. Ele não
copia os cinco campos da âncora: Evidence/Artifact históricos preservam os
valores reconstituídos usados na avaliação.

A migration:

- será posterior a `20260814_11`;
- não reescreverá a migration F5.1;
- preservará todos os dados existentes;
- acrescentará somente chaves candidatas, constraints, FKs e índices
  necessários;
- terá teste de upgrade, metadata, downgrade protegido e regressão F5.1.

Não existe terceira tabela de lifecycle. O encadeamento da Claim e a auditoria
preservam a correção nesta unidade.

### 13. Atomicidade e auditoria

Claim, conjunto completo de links e evento de auditoria de sucesso pertencem ao
mesmo commit. Falha antes do commit não pode deixar Claim ou link parcial.

Auditoria usa o recurso `INVESTIGATION` já existente e códigos fechados. Ela
registra ator, workspace, Investigation, ação, resultado, razão, correlação e
instante. Predicate, valor, temporalidade, conteúdo, locator, origem, decisão de
uso detalhada e digests não entram no evento.

Negação e falha conhecida seguem o padrão coordenado já aceito. Recurso
cross-tenant não tem seu ID copiado para auditoria.

### 14. Concorrência e ordem de locks

A ordem proposta é:

1. lock tenant-scoped do command ID da Claim;
2. em `CorrectClaim`, lock da versão-alvo/história da Claim;
3. locks das versões de Evidence, ordenados de forma crescente por Evidence ID;
4. releitura e validação integral de todas as histórias;
5. construção integral de Claim e links;
6. primeiro append;
7. auditoria e commit único.

O lock de Evidence deve reutilizar o mecanismo de história da F5.1. Como
correção e revogação de Evidence também bloqueiam a versão-alvo, uma Claim não
pode ser confirmada concorrentemente contra uma versão que mudou sem que uma
das operações revalide e falhe fechado.

Nenhum serviço de Evidence adquire lock de Claim. A direção única e a ordenação
de múltiplas Evidence evitam ciclos entre `RegisterClaim`, `CorrectClaim`,
correção de Evidence e revogação de Evidence.

### 15. Tenancy e segurança

- toda leitura filtra primeiro por `actor.workspace_id`;
- FKs compostas repetem workspace, Investigation, Company e decisão;
- entradas usam IDs fortes, enums fechados e snapshots limitados;
- valores e conteúdo são excluídos de `repr`, erros, logs e auditoria;
- mappers reconstituem domínio e recalculam digests;
- JSONB, se usado para `ClaimValue`, contém schema fechado e versionado;
- não há rede, filesystem, upload, parser, modelo, segredo ou código externo;
- nenhum texto de Evidence é tratado como instrução;
- source snapshots não são interpretados como aprovação;
- hash isolado do Artifact não concede confiança;
- somente âncora completa, proveniente de fixture sintética rastreável, pode
  avançar para elegibilidade;
- ausência/diferença de âncora e falha de integridade não são confundidas.

## Consequências

- Claim e Evidence permanecem agregados distintos e rastreáveis.
- A decisão contextual não corrompe o vocabulário de admissibilidade global.
- Correções e mudanças de links preservam integralmente o histórico.
- Assessment corrente reage a supersessão/revogação sem update ou cache.
- Uma Claim insuficiente pode ser preservada sem ser promovida a fato.
- Contradição local é visível sem escolher automaticamente uma verdade.
- Duas tabelas bastam para a unidade proposta.
- Um manifesto interno versionado fornece raiz de confiança para combinações
  sintéticas exatas de Artifact, conteúdo localizado e locator, sem alterar
  Artifact/Evidence nem criar tabela.
- A configuração conservadora V1 admite somente `EXCERPT_ONLY`, `INDEFINITE`,
  `FULL` e `content_original` íntegro.
- Fixtures rastreáveis permitem recomputar independentemente todas as âncoras e o
  digest do manifesto.
- O outcome é reproduzível e não pode ser imposto por `OWNER` ou `ADMIN`.
- Predicate/version permanecem estáveis em toda a série da Claim.
- Manifesto/política foram implementados e recomputados independentemente.
- O fluxo runtime continua sem caminho materializado até `VERIFYING`.

## Alternativas rejeitadas

- **Reutilizar `ADMISSIBLE` no link:** conflita com a admissibilidade global da
  Evidence e sugere promoção que não ocorreu.
- **Atualizar `Evidence.admissibility_status`:** viola ADR 0024 e mistura
  custódia com uso contextual.
- **Criar Claim em `COLLECTING`:** contradiz o lifecycle documental vigente.
- **Persistir `SUPPORTED`/`CONFLICTED`:** cria estado obsoleto após mudança da
  Evidence e exige sincronização não autorizada.
- **Apontar link para series/latest:** perde a versão e o digest usados.
- **Atualizar links históricos:** destrói reprodutibilidade.
- **Terceira tabela de lifecycle:** é desnecessária para correção por versão e
  amplia a subfase.
- **Confiar em `source_id`, prefixo sintético, `FILE_IMPORT` ou método de
  aquisição:** esses campos não provam autorização de corpus.
- **Confiar somente em `Artifact.original_content_sha256`:** bytes originais
  conhecidos não comprovam conteúdo localizado nem locator da Evidence.
- **Criar canonicalização própria de locator na F5.2:** permitiria divergência
  semântica em relação a `locator_to_canonical_json` da F5.1.
- **Eliminar duplicatas do manifesto silenciosamente:** mascara configuração
  ambígua; entradas normalizadas idênticas devem invalidar o manifesto.
- **Aceitar magic hashes sem fixture:** impede recomputação independente da raiz
  de confiança.
- **Generalizar modes na V1:** aumenta combinações de retenção/exibição sem
  necessidade para o corpus sintético controlado.
- **Aceitar outcome, razão ou digest do manifesto no comando:** permite ao ator
  transformar Evidence arbitrária em elegível e quebra determinismo.
- **Manifesto em tabela, arquivo mutável ou variável de ambiente:** cria raiz de
  confiança alterável em runtime e amplia persistência/operação.
- **Tratar entrada no manifesto como aprovação de fonte:** confunde bytes
  sintéticos internos com autenticidade externa e Gate G6.
- **Alterar predicate durante correção:** muda o significado da série; predicate
  diferente exige nova Claim.
- **Criar papel REVIEWER agora:** exige mudança de identidade/workflow fora do
  recorte.
- **Permitir proposta por ANALYST:** exige separação entre proposta e decisão.
- **Resolver contradição por precedência/confiança:** antecipa revisão e escolha
  factual.

## Itens adiados

- admissibilidade global da Evidence;
- fontes reais e Gate G6;
- transições até `VERIFYING`;
- consulta histórica `as of` e reconstrução temporal do assessment;
- cache ou snapshot de assessment;
- rejeição humana de Claim e `ReviewDecision` genérica;
- override humano de elegibilidade;
- papel `REVIEWER` e proposta por `ANALYST`;
- grupos globais de conflito e precedência entre claims;
- escolha de Claim verdadeira;
- predicates além dos cinco estruturais V1;
- extração, derivação, IA, risco, scoring, relatório e exportação;
- API, frontend, jobs, workers, filas, scheduler, outbox e fan-out/fan-in;
- F5.3.

## Parecer independente e correções de fechamento

A revisão independente de 2026-08-22 emitiu `APPROVED_WITH_FIXES`. A inspeção
direta confirmou quatro achados, corrigidos no mesmo gate:

1. snapshots JSON de valor e temporalidade aceitavam coerção por `str()` e
   campos desconhecidos; agora exigem conjunto exato de chaves, tipos JSON
   exatos e round-trip canônico;
2. leitura histórica omitia `FAILED` e `CANCELLED`; ambos passaram a ser
   legíveis, sem ampliar a mutação além de `VERIFYING`;
3. `ClaimHistory` não vinculava `requested_by`/`evaluated_at` a
   `created_by`/`created_at`; a proveniência agora é invariante do agregado;
4. assessment com múltiplas Evidences podia reler estados sob snapshots de
   statements diferentes; todos os history locks são adquiridos em ordem
   canônica antes da releitura.

A revisão recomputou bytes, conteúdo, locator e manifesto diretamente da
fixture sintética, confirmou digest
`535509a811baf90ccbe60651ec73a9c18b5260597f69a05762f6451fc8314c7c`,
executou regressão F5.1, PostgreSQL, migrations e o quality gate integral. F5.3
permanece não autorizada.

## Critérios objetivos de aceitação

O aceite exige, e o gate independente comprovou:

1. manifesto interno e política serem implementados com
   `ControlledEvidenceAnchorV1`, digest canônico verificado, fixtures
   rastreáveis e sem entrada mutável ou controlada por comando;
2. task F5.2 revisada e autorização explícita de implementação;
3. domínio puro com predicates/valores/links/assessment fechados;
4. Evidence F5.1 permanecer `PENDING` e inalterada;
5. duas tabelas append-only com FKs tenant-scoped e migration nova;
6. Claim e links validados antes do primeiro append;
7. concorrência Claim×Evidence coberta com ordem determinística de locks;
8. autorização e auditoria redigida comprovadas;
9. assessment corrente falhar fechado em supersessão, revogação e adulteração;
10. unitários, PostgreSQL, migration, arquitetura, segurança e regressão F5.1
    aprovados;
11. módulo `claims` atingir ao menos 90% de branch coverage e cobertura global
    permanecer acima do gate vigente;
12. lint, formatação, tipos, scanner, builds, pacote limpo e revisão independente
    aprovados;
13. nenhuma capacidade adiada ou F5.3 ter sido iniciada;
14. outcomes serem gerados somente pela política e nunca fornecidos por ator;
15. correção preservar `predicate_code` e `predicate_version` da série;
16. `ELIGIBLE` exigir match exato dos cinco campos da âncora, nunca apenas do
    hash do Artifact;
17. duplicatas normalizadas invalidarem o manifesto;
18. policy V1 restringir storage/retention/display a
    `EXCERPT_ONLY`/`INDEFINITE`/`FULL` e exigir `content_original` íntegro.

Todos os critérios aplicáveis foram cumpridos no gate independente. Este aceite
autoriza somente o fechamento da F5.2; não conclui a Fase 5/G4, não altera o
Gate E2E e não autoriza F5.3.
