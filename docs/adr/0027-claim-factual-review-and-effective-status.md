# ADR 0027 — Revisão factual interna de Claim e status efetivo

- Status: Accepted
- Data: 2026-08-24
- Decisores: responsável pelo projeto
- Relacionados: ADR 0003, ADR 0008, ADR 0011, ADR 0013 e ADR 0023–0026

## Contexto

F5.1 materializou cadeia de custódia, F5.2 Claims e links contextuais, e F5.3 a admissibilidade global temporal de Evidence. Nenhuma entrega torna Claim factual, verdadeira ou reportável. O `ReviewDecision` genérico previsto em `docs/data-model.md` não preserva vínculo suficiente com versão da Claim, links e admissibilidade; este ADR o substitui como placeholder arquitetural para Claim review.

## Decisão

F5.4 materializa `ClaimReviewDecision`, humano e append-only, para o único purpose V1 `INTERNAL_FACTUAL_CLAIM_USE`. Aceite significa exclusivamente que a versão exata da Claim foi aceita sob policy F5.4 V1 e base factual vinculada. Não significa verdade, publicação, reportabilidade, exportação, crédito, risco, scoring, recomendação ou aprovação externa.

As camadas são independentes: F5.2 `ELIGIBLE` para `INTERNAL_CLAIM_VERIFICATION`; F5.3 `ADMISSIBLE` para `INTERNAL_FACTUAL_EVIDENCE_USE`; F5.4 `ACCEPTED_FOR_INTERNAL_FACTUAL_USE` para `INTERNAL_FACTUAL_CLAIM_USE`. Nenhuma implica automaticamente a seguinte.

O modelo especializado contém IDs de decisão/contexto, Claim ID/série/versão/digest, sequência/predecessor, outcome/razão, policy/versão/purpose, `review_basis_digest`, command ID/digest, decisor/instante, schema e decision digest. O comando `DecideClaimReview` recebe `ACCEPT`, `REJECT` ou `RETURN_FOR_CORRECTION`; a policy produz, respectivamente, `ACCEPTED_FOR_INTERNAL_FACTUAL_USE`, `REJECTED_FOR_INTERNAL_FACTUAL_USE` ou `NEEDS_CORRECTION`. A action não é persistida enquanto esse mapeamento V1 for um-para-um. Não existem outcomes `TRUE`, `FALSE`, `VERIFIED_TRUE` ou `PROVEN`.

## Gate factual e review basis

Uma Evidence vinculada conta apenas quando o `ClaimEvidenceLink` F5.2 exato é `ELIGIBLE` e a Evidence exata tem status efetivo F5.3 `ADMISSIBLE` no cutoff. Ambas são necessárias e nenhuma basta isoladamente; admissibilidade global não pode contornar link `RESTRICTED` ou `REJECTED`. A regra vale para `SUPPORTS`, `CONTRADICTS` e `QUALIFIES` quando considerados.

`review_basis_digest` é snapshot histórico, sempre calculado com `basis_as_of = decision.decided_at`, e usa `CLAIM_REVIEW_BASIS_SCHEMA_V1`. Seu payload canônico contém Claim ID/série/versão/digest e conjunto completo, ordenado deterministicamente, de links: `link_digest`, role, Evidence ID/digest, resultado contextual protegido no link e status/decisão F5.3 aplicável naquele cutoff. Nenhum estado futuro entra no payload e não há Clock oculto. Não inclui conteúdo, locator, ClaimValue, hashes de conteúdo, texto factual ou metadados de fonte.

`ACCEPT` exige história/links/contexto íntegros, versão atual, base calculável, pelo menos um `SUPPORTS` simultaneamente `ELIGIBLE` e `ADMISSIBLE`, Evidence exata não expirada/revogada/supersedida, nenhuma `CONTRADICTS` também válida, policy/purpose, autorização e self-review válidos, e ausência de dependência stale/desconhecida. Zero suporte válido bloqueia aceite. Suporte e contradição válidos bloqueiam aceite e permitem rejeitar ou devolver. `QUALIFIES` é informativo: V1 não infere materialidade; o humano pode devolver para correção, e incompatibilidade factual deve ser `CONTRADICTS` em nova versão.

`STANDARD` e `CRITICAL` compartilham baseline conservador: suporte válido e ausência de contradição válida. Para `CRITICAL`, haverá testes explícitos de bloqueio sem suporte, por contradição e de revisão humana obrigatória. Não são criados pesos, tiers, maiorias ou limiares.

## História, validade e projeção efetiva

Há história append-only por versão exata: sequência inicial 1 sem predecessor, demais contíguas e na mesma Claim/série/versão/workspace. O intervalo da versão é `[claim.created_at, next_claim_version.created_at)`. Mutation atua apenas sobre versão vigente; correção cria nova versão `PENDING`, sem herdar review ou base.

`validate_persisted_claim_review(...)` e `project_effective_claim_review(..., as_of)` são operações conceitualmente distintas. A primeira reconstrói a base em `decision.decided_at`, recalcula o digest histórico e prova que a decisão era semanticamente legítima quando criada. Divergência nesse replay histórico é tamper/integridade persistida e falha fechado; mudança legítima posterior não é tamper.

`EffectiveClaimReview(as_of)` é puro e não persistido: `PENDING`, `ACCEPTED`, `REJECTED`, `NEEDS_CORRECTION` ou `INVALIDATED`. Depois de validar a decisão histórica, a projeção examina o intervalo `(decision.decided_at, as_of]`. Uma decisão positiva se torna monotonicamente `INVALIDATED` se qualquer dependency já registrada na base mudar de modo incompatível: suporte deixa de ser `ELIGIBLE` + `ADMISSIBLE`, suporte expira/é revogado/é supersedido, decisão F5.3 aplicável muda, contradição vinculada se torna válida ou uma história de dependency deixa de ser semanticamente válida. `QUALIFIES` não invalida por julgamento oculto de materialidade, e Evidence não vinculada não altera Claim automaticamente.

Essa regra é conservadora para múltiplos suportes: a mudança material em qualquer dependency factual registrada na base positiva invalida o aceite, mesmo que outro suporte ainda satisfaça o mínimo da policy. O humano revisou exatamente a base identificada. Uma nova decisão positiva cria novo review epoch e é o único mecanismo que pode restaurar `ACCEPTED`; retorno posterior da Evidence a `ADMISSIBLE` não reativa decisão antiga.

Não há retroatividade: se aceite em T1 e revogação em T2, `as_of` entre T1 e T2 é `ACCEPTED`, e `as_of >= T2` é `INVALIDATED`. Se a Evidence expira em T2 e é readmitida em T3, a decisão de T1 permanece `INVALIDATED` desde T2. Correção da Claim em T2 seleciona a versão nova `PENDING`; a versão anterior e suas reviews continuam somente históricas, sem ser tratada como tamper.

`REJECTED_FOR_INTERNAL_FACTUAL_USE` e `NEEDS_CORRECTION` são decisões fail-safe. Não exigem positive factual gate, suporte válido ou ausência de contradição; exigem Claim corrente no instante, história/link set/contexto íntegros, intervalo, predecessor, policy/purpose, autorização e idempotência válidos. Também preservam `review_basis_digest` histórico, sem afirmar que a base passava o gate positivo. Para a mesma versão, não são invalidadas automaticamente por mudança posterior de Evidence: permanecem efetivas até nova decisão ou correção.

Read, replay e supersession revalidam Claim/intervalo/links/digests, outcomes F5.2, Evidence/histórias, decisões F5.3 semanticamente válidas, admissibilidade temporal, suporte, contradições, base, self-review, policy/purpose e decision digest. FKs, checks e digests isolados não bastam. Mesmo command ID/digest é replay sem clock, ID, auditoria ou append; digest diferente é collision.

## Concorrência, autorização e persistência

Mutation adquire: command lock; Claim history; Evidence histories por ID canônico; admissibility histories na mesma ordem; Claim review history; releitura; validação; policy; digest; append/auditoria/commit. Read em `READ COMMITTED` estabiliza Claim/versão e link set, bloqueia Evidence/admissibilidade/review nessa ordem, relê, valida a base histórica e examina mudanças até `as_of`. Não introduzir ordem `Evidence -> Claim` nem lock por evento individual.

`ACCEPT` exige `decided_by != Claim.created_by` da versão exata. `REJECT` e `RETURN_FOR_CORRECTION` podem ser feitos pelo criador. Não criar `REVIEWER`, `PROPOSE`, last-corrector ou restrição extra sobre autor da Evidence/decisor F5.3. Permissões tenant-scoped futuras: `CLAIM_REVIEW_READ`, `CLAIM_REVIEW_ACCEPT`, `CLAIM_REVIEW_REJECT`, `CLAIM_REVIEW_RETURN_FOR_CORRECTION`, `CLAIM_REVIEW_SUPERSEDE`; OWNER/ADMIN todas, ANALYST/VIEWER leitura. Autorizar antes de lookup enumerável. Auditoria usa catálogos fechados e não registra ClaimValue, conteúdo, locator, hash, fonte ou justificativa livre.

O desenho inicial usa apenas `claim_review_decision`, append-only, sem tabela de status. FKs compostas fixam a mesma linha real de Claim; predecessor é scoped à versão; command/sequence têm unicidade e checks; índices são tenant-first. Candidate key na Claim só será criada se a FK completa exigir. Não altera semântica de Claim, Evidence ou F5.3.

## Limites, ameaças e critérios

Derivation não pertence a F5.4 nem é requisito G4 sem transformação habilitada; OCR, tradução, extração e cálculo exigirão subfase própria antes de seu uso. F5.4 fecha G4 após implementação e aceite independente aprovados; não fecha G6, Gate E2E, fontes reais, relatório ou piloto.

Os testes implementados cobrem self-review, outcome controlado pelo ator, laundering F5.2/F5.3, decisões forjadas/stale, correção/revogação/expiração/supersessão, contradições, `QUALIFIES`, auto-reativação, basis drift, cross-tenant, IDOR, replay, snapshot misto, deadlock, leakage e mutação destrutiva. Eles provam aceite antes e invalidação no cutoff do evento, não reativação por readmissão futura, novo aceite restaurando efeito, digest histórico válido após mudança legítima, tamper histórico fail-closed, decisões negativas sem gate positivo e persistentes, correção iniciando `PENDING`, Evidence não vinculada inócua e a regra de múltiplos suportes. O ADR foi aceito após implementação restrita, migration, testes, quality gates e revisão independente aprovada.

## Alternativas rejeitadas

- `ReviewDecision` genérico: não preserva base factual e temporal necessária.
- Somente `ELIGIBLE` ou somente `ADMISSIBLE`: contorna uma fronteira.
- Status factual persistido: confunde decisão histórica e efeito atual.
- Copiar Evidence em child table: duplica história sem necessidade.
- Materialidade implícita, maioria ou reativação automática: inventam política ou ignoram a revisão humana.
- Usar estado atual para recalcular base histórica: confunde mudança legítima posterior com tamper.
