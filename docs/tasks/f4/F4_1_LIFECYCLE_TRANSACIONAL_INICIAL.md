# F4.1 — Lifecycle transacional inicial da investigação

Status: **ACEITA APÓS REVISÃO INDEPENDENTE**.

## 1. Autorização e objetivo

A instrução de 2026-07-29 aceitou a F3.3, o gate G3 e a Fase 3 e autorizou
exclusivamente a F4.1. O objetivo é tornar duas mudanças de estado duráveis,
concorrentes e auditáveis sem iniciar a F4.2.

## 2. Comportamentos materializados

- `StartIdentification`: exige estado `CREATED`, versão esperada e
  `IdentificationInput`; produz `IDENTIFYING`, `started_at = occurred_at`,
  `completed_at = None` e versão anterior + 1.
- `CancelInvestigation`: exige estado não terminal, versão esperada e razão
  fechada; em `CREATED`, início e término recebem o mesmo instante; após início,
  preserva `started_at` e define `completed_at`.

Não existe `transition_to(state)` ou equivalente. Terminal nunca reabre.

## 3. Entrada de identificação

O schema `1` suporta nomes jurídico/comercial, identificadores tipados,
domínio corporativo, endereço/localidade fechados e idioma original. Valores
originais são preservados separadamente dos normalizados. Países usam
`CountryCode`; domínio não aceita esquema, path, query ou fragmento. Documento,
token, cookie, segredo, URL arbitrária e payload externo não pertencem ao
contrato.

A entrada é dataclass congelada, possui resumo/repr redigidos, JSON canônico e
digest SHA-256. Sem empresa confirmada, ao menos um sinal utilizável é
obrigatório. O mapper valida schema, forma canônica e digest ao reconstituir.

## 4. Aplicação, autorização e erros

O `InvestigationService` autoriza antes de buscar comando ou investigação.
`OWNER`, `ADMIN` e `ANALYST` podem iniciar/cancelar; `VIEWER` é negado. Erros
públicos distinguem recurso ausente, transição inválida, conflito de versão e
colisão de comando sem expor existência cross-tenant ou conteúdo empresarial.

O `Clock` é lido uma vez somente para transição efetiva. Replay não lê relógio,
não consulta/agrega estado para atualizar e não gera segunda auditoria de
sucesso.

## 5. Persistência e atomicidade

`InvestigationRepository.update_if_version` faz CAS por tenant, ID e versão e
altera apenas `state`, `state_version`, timestamps e snapshot de entrada. O
ledger `investigation_transition` é append-only e usa unicidade
`(workspace_id, command_id)`, foreign key composta para investigação/tenant,
checks de comando/transição/versão/digest e índices de consulta.

Um advisory transaction lock serializa o mesmo comando antes do lookup.
Comando/digest idênticos retornam o resultado registrado; conteúdo diferente
com o mesmo ID gera colisão. CAS, ledger e auditoria compartilham o mesmo UoW e
commit; falha em qualquer etapa reverte tudo.

## 6. Migration e compatibilidade

`20260729_03_add_investigation_lifecycle_foundation.py` sucede a revisão
`20260728_02`, adiciona colunas nullable e a tabela do ledger, e possui downgrade
real. A constraint de entrada para estados iniciados é `NOT VALID` para não
corromper ou inventar conteúdo em linhas históricas; novas escritas continuam
protegidas. A reconstituição admite explicitamente esse formato legado, mas o
comando novo nunca o produz. Migrations anteriores não foram alteradas.

## 7. Testes e segurança

Testes unitários cobrem entrada, domínio, comandos, replay, colisão, autorização,
clock e rollback por falha de ledger/auditoria/commit. PostgreSQL real cobre
round-trip, CAS correto/desatualizado/cross-tenant, reinício de UoW, constraints,
migration e duas corridas com `Barrier`, sem sleeps: uma versão tem um vencedor;
um comando concorrente tem um efeito e um replay.

Guardas AST impedem I/O, ambiente, runner F3.3, API genérica de transição,
pacotes de fase posterior, mutação do ledger e snapshot na auditoria.

## 8. Exclusões e pendências

Não foram criados planner, job, fila, worker, outbox, candidato, matching,
resolução, revisão humana, execução de conector, propagação de cancelamento,
endpoint, autenticação, evidência, claim, scoring ou reporting. A constraint
histórica `NOT VALID` requer reconciliação futura antes de validação global.
F4.2 exige aceite independente da F4.1 e autorização explícita.
