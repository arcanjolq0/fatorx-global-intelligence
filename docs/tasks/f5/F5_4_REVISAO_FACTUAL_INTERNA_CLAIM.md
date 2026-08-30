# F5.4 — Revisão factual interna de Claim

## Status e baseline

**NOT_STARTED.** Implementação futura governada pelo ADR 0027, cujo status é `Proposed`. Baseline: `main` e `origin/main` em `27200988c3762fcd0196ae81ba6d10e9d6b8ecea`, migration head `20260822_13`; F5.1/F5.2/F5.3 fechadas e ADRs 0024–0026 `Accepted`; G4 aberto.

## Objetivo e escopo

Implementar decisão humana append-only sobre versão exata de Claim para `INTERNAL_FACTUAL_CLAIM_USE`. Outcome positivo é aceite para uso factual interno, não verdade, reportabilidade, publicação, exportação, crédito, risco, scoring, recomendação ou aprovação externa.

Inclui domínio `ClaimReviewDecision`, comando `DecideClaimReview`, policy V1, `review_basis_digest`, `EffectiveClaimReview(as_of)`, portas/UoW, PostgreSQL/migration, autorização/auditoria, replay, concorrência e testes. Exclui Derivation, lifecycle/transições, fonte real, HTTP, jobs, API, frontend, IA, risco, scoring, relatório, F5.5/F6 e status factual persistido.

## Domínio, policy e review basis

O comando recebe `ACCEPT`, `REJECT` ou `RETURN_FOR_CORRECTION`; o serviço deriva os outcomes fechados `ACCEPTED_FOR_INTERNAL_FACTUAL_USE`, `REJECTED_FOR_INTERNAL_FACTUAL_USE` e `NEEDS_CORRECTION`. Não persistir requested action enquanto o mapeamento V1 for um-para-um, e nunca criar `TRUE`, `FALSE`, `VERIFIED_TRUE` ou `PROVEN`.

Uma Evidence conta apenas quando o link F5.2 exato for `ELIGIBLE` e a Evidence exata estiver F5.3 efetivamente `ADMISSIBLE` no cutoff. A regra vale para suporte, contradição e qualificação; cada condição isolada falha. `ACCEPT` requer suporte válido, ausência de contradição válida, histórias/contexto íntegros, versão atual, policy/purpose, autorização, self-review e ausência de estado stale/desconhecido. `QUALIFIES` é informativo sem regra oculta de materialidade. `STANDARD` e `CRITICAL` exigem o mesmo baseline; críticos terão testes explícitos de bloqueio e revisão humana.

Persistir contexto, Claim ID/série/versão/digest, sequência/predecessor, outcome/razão, policy/purpose, review basis, command, ator/instante, schema e digest. `review_basis_digest` é snapshot com `basis_as_of = decision.decided_at` e schema canônico V1; inclui Claim e conjunto completo/ordenado de links, seus digests/roles/Evidence, decisão contextual e estado/decisão F5.3 nesse cutoff. Nunca inclui conteúdo, locator, ClaimValue, texto factual ou fonte, nem estado futuro.

## História, projeção e revalidação

Decisão ocorre em `[claim.created_at, next_claim_version.created_at)` e apenas na versão vigente. Correção cria nova versão `PENDING` sem herdar review ou base. A projeção pura é `PENDING`, `ACCEPTED`, `REJECTED`, `NEEDS_CORRECTION` ou `INVALIDATED`.

Separar `validate_persisted_claim_review(...)`, que reconstrói e valida a base em `decision.decided_at`, de `project_effective_claim_review(..., as_of)`, que examina o intervalo posterior. Digest histórico divergente é tamper e falha fechado; mudança legítima posterior é invalidação, não corrupção. Aceite é monotonicamente invalidado por mudança incompatível em qualquer dependency factual registrada: suporte perde link gate, expira/é revogado/supersedido, F5.3 muda, contradição vinculada torna-se válida ou história fica inválida. Essa regra vale mesmo com múltiplos suportes ainda válidos, pois o humano revisou toda a base. Nova decisão positiva é o único mecanismo de restauração; readmissão futura não reativa review antiga. Evidence não vinculada e `QUALIFIES` sem materialidade estruturada não invalidam automaticamente.

Decisões negativas são fail-safe: não exigem gate positivo, mas exigem Claim/history/link set/contexto/intervalo/predecessor/policy/autorização/idempotência íntegros. Também persistem `review_basis_digest`, sem declarar base positiva. Permanecem efetivas até nova decisão ou correção, apesar de mudanças posteriores na Evidence.

Em read, replay e supersession, revalidar semanticamente Claim/intervalo/links/digests, F5.2, Evidence/histórias, F5.3, admissibilidade temporal, suporte, contradições, basis, self-review, policy/purpose e decision digest. A validação histórica usa somente o cutoff original; a projeção atual examina mudanças depois dele. Divergência histórica falha fechado.

## Ports, PostgreSQL, authorization e audit

Criar repositório append-only de decisão, locks de command/história, consulta por command e reconstituição, integrado por UoW. A migration criará somente `claim_review_decision`, com FK composta à versão exata da Claim, predecessor scoped, command uniqueness, checks, índices tenant-first e downgrade seguro. Candidate key na Claim só se necessária. Não mudar Claim, Evidence ou F5.3; não criar tabela de status.

Permissões: `CLAIM_REVIEW_READ`, `CLAIM_REVIEW_ACCEPT`, `CLAIM_REVIEW_REJECT`, `CLAIM_REVIEW_RETURN_FOR_CORRECTION`, `CLAIM_REVIEW_SUPERSEDE`. OWNER/ADMIN têm todas; ANALYST/VIEWER leem. Autorizar antes do lookup. Aceite exige decisor diferente de `Claim.created_by` da versão exata; criador pode rejeitar/devolver. Auditoria redigida não armazena valor, conteúdo, locator, hash, fonte ou justificativa livre.

## Replay, concorrência e testes

Mesmo command ID/digest é replay sem clock, novo ID, auditoria ou append; digest divergente é collision. Locks: command; Claim; Evidences ordenadas; admissibility histories na mesma ordem; review history; releitura e validação. Read em `READ COMMITTED` estabiliza versão/link set, relê nessa ordem, valida base histórica e examina o intervalo até `as_of`, sem locks por evento. Não introduzir ordem `Evidence -> Claim`.

Planejar domínio, policy, self-review, authorization/audit/tenancy, tamper, `as_of`, replay, PostgreSQL/migration, regressões F5.1–F5.3 e arquitetura. Incluir aceite antes e invalidação no cutoff, não reativação por readmissão, novo aceite restaurando efeito, digest histórico válido após mudança legítima, tamper histórico fail-closed, decisões negativas sem gate positivo/persistentes, base negativa preservada, correção `PENDING`, Evidence não vinculada, `QUALIFIES` sem materialidade oculta e múltiplos suportes com regra conservadora. Cobrir com barriers/events as corridas review/read contra Claim correction, Evidence correction/revoke, F5.3 supersession, review e replay; sem sleeps arbitrários. Executar testes, lint, formatação, tipos, scanner de segredos, build, cobertura vigente e revisão independente.

## Gate G4 e limites

F5.4 pode fechar G4 somente após implementação e aceite independente que prove revisão humana e gate factual. Não fecha G6, Gate E2E, fontes reais, relatórios ou piloto. Derivation é subfase posterior obrigatória antes de qualquer transformação de conteúdo, mas não é requisito atual de F5.4 ou G4.
