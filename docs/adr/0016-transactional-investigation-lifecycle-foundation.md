# ADR-0016 — Fundação transacional do lifecycle de investigação

- Status: Accepted
- Data: 2026-07-29

## Contexto

O ADR-0006 define lifecycle persistido, optimistic locking e idempotência, mas
as fases anteriores somente validavam snapshots. A F4.1 precisa materializar
`CREATED -> IDENTIFYING` e cancelamento sem antecipar planner, jobs, candidatos,
matching ou execução de conectores. Também precisa preservar investigações
históricas que não possuíam entrada estruturada.

## Decisão

### Comandos e domínio

A aplicação expõe somente `StartIdentification` e `CancelInvestigation`.
`Investigation.start_identification()` e `Investigation.cancel()` são operações
puras: recebem o instante confiável, retornam novo snapshot imutável mais uma
transição tipada, incrementam `state_version` exatamente uma vez e nunca geram
UUID, fazem I/O ou aceitam estado destino arbitrário.

### Entrada versionada em JSONB

`IdentificationInput` é um envelope fechado e imutável de schema `1`. Ele
separa valores originais e normalizados, tipa identificadores, domínio e
endereço, valida coerência de país e exige sinal utilizável quando não há
empresa confirmada. A serialização é JSON canônico e possui digest SHA-256.

O agregado persiste `input_snapshot JSONB`, `input_schema_version` e
`input_digest`. JSONB é usado somente para esse envelope versionado, não como
modelo genérico. `CREATED` mantém os três campos nulos. Reconstituição recompõe
o tipo, recalcula schema/digest e rejeita conteúdo divergente. Alterar o schema
exigirá nova versão e estratégia explícita de leitura/migração.

### Ledger e idempotência

`investigation_transition` é append-only e registra tenant, investigação,
`command_id`, tipo fechado, estados/versões, ator, razão fechada, instante,
correlação e digest canônico allowlisted. `(workspace_id, command_id)` é único.
O repositório oferece somente lock transacional, lookup tenant-scoped e append.

Antes da leitura de replay, um advisory transaction lock derivado de tenant e
comando serializa concorrentes com o mesmo ID. Digest idêntico devolve o
registro persistido sem relógio, CAS, incremento ou nova auditoria; digest
divergente produz colisão tipada. O digest inclui semântica do comando e ator,
mas exclui correlação de retry, horário, `repr`, segredo e conteúdo não
allowlisted.

### CAS e atomicidade

O update do agregado filtra simultaneamente `workspace_id`, `id` e
`state_version` esperada e altera somente campos do lifecycle. `rowcount == 1`
é sucesso; zero é conflito seguro, sem retry automático. CAS, append no ledger
e auditoria de sucesso usam a mesma conexão, transação e chamada de `commit`.
Qualquer falha posterior provoca rollback integral.

Autorização ocorre antes do lookup do recurso. `OWNER`, `ADMIN` e `ANALYST`
podem executar os dois comandos; `VIEWER` não. Auditoria contém somente IDs,
códigos fechados, outcome, correlação e instante — nunca snapshot, nome,
identificador, endereço ou domínio.

### Compatibilidade de migration

A revisão adiciona colunas nullable e uma tabela nova sem reescrever migrations.
A constraint que exige entrada ou empresa em estados iniciados é criada
`NOT VALID`: preserva linhas históricas sem fabricar entrada, mas é aplicada a
novas inserções e atualizações. As demais constraints são validadas
imediatamente. Downgrade remove somente os artefatos F4.1 e preserva o agregado.
O contrato de reconstituição continua aceitando a ausência nos snapshots
históricos; toda transição `StartIdentification` nova continua exigindo entrada
tipada, e toda nova linha iniciada é protegida pela constraint.

## Consequências

- Replays sobrevivem a novos UoWs e reinícios de processo.
- Duas transações na mesma versão não sobrescrevem uma à outra.
- O snapshot original permanece auditável e redigível sem criar tabelas de
  candidatos ou entidades canônicas.
- Advisory lock é local ao PostgreSQL e pressupõe que todas as escritas usem o
  serviço/contrato; a unique constraint permanece a defesa final.
- O ledger não possui update/delete de fluxo comum; retenção futura exige
  política e registro auditável.
- Linhas históricas cobertas pela constraint `NOT VALID` devem ser reconciliadas
  antes de eventual `VALIDATE CONSTRAINT`; não existe backfill admissível agora.
- F4.1 não executa conectores, não propaga cancelamento e não implementa
  transições posteriores. F4.2 permanece dependente de autorização explícita.
