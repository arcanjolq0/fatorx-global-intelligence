# ADR-0006 — Máquina de estados persistida

- Status: Accepted
- Data: 2026-07-25

## Contexto

Investigações longas enfrentam espera humana, falhas parciais, retries, cancelamento e concorrência. Estados informais gerariam relatórios inconsistentes.

## Decisão

Usar estados definidos em `investigation-lifecycle.md`, transições por comandos, eventos/auditoria, optimistic locking e idempotência. Jobs possuem lifecycle próprio. `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED` e `CANCELLED` são terminais.

## Consequências

- Retomada e falha parcial tornam-se testáveis.
- Workers não avançam o agregado diretamente.
- Mudança de transição exige atualização de contrato, testes e eventualmente migration.
- Reinvestigação cria novo agregado em vez de reabrir terminal.
