# F4.6 — Execução direta controlada de uma operação de coleta

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE, INCLUINDO F4.6.1/F4.6.2.** A autorização
explícita foi recebida em 2026-08-11. A Fase 4 permanece em andamento e nenhuma
subfase posterior está autorizada.

## Objetivo

Consumir exatamente uma `CollectionOperation` imutável por comando e executar
somente `SEARCH` por meio do runner F3.3, com um conector explicitamente
fornecido, admitido por allowlist e capaz de operar em `TEST`. O corte prova a
fronteira direta entre manifesto e simulador sem criar jobs, filas, workers,
scheduler, outbox, fan-out ou descoberta dinâmica.

## Contrato implementado

- `ExecuteCollectionSearchOperation` referencia run/operação e exige os digests
  esperados, locales, versão de política da fonte e política de execução;
- OWNER, ADMIN e ANALYST podem executar; VIEWER é negado;
- run e operação precisam continuar íntegros, tenant-scoped e `PENDING`;
- dependências, quando existirem, precisam possuir conclusão anterior utilizável;
- descritor, versões, fonte, cobertura, acesso e operações precisam coincidir
  exatamente com o snapshot do manifesto;
- somente `SEARCH` e `ConnectorMode.TEST` são aceitos;
- prazo civil e budget restante são revalidados antes do ownership;
- a query é derivada exclusivamente da Company canônica persistida;
- o ownership imutável é confirmado antes do I/O; a conclusão redigida é acrescentada
  em transação posterior;
- replay concluído devolve o mesmo registro sem clock, conector ou escrita;
- mesmo `command_id` com conteúdo diferente é colisão; ownership sem conclusão é
  reportado como execução em andamento.

## Persistência

A migration `20260811_10` acrescenta:

- `collection_operation_execution`: ownership único por operação, comando,
  ator, descritor, source policy, locales, política de execução, instante e
  digests;
- `collection_operation_execution_result`: outcome, erro/warnings fechados,
  accounting agregado, fingerprint/digest, idempotência, controle e instante.

As duas tabelas são append-only pelas portas públicas, possuem FKs compostas por
tenant e downgrade fail-safe. Não há coluna para itens, candidatos, observações,
artefatos, texto empresarial ou payload do conector.

## Semântica deliberada

O manifesto original não é alterado: run/operação continuam `PENDING` e tentativa
zero. O ownership e a conclusão formam histórico operacional preparatório, não um
`ConnectorRun`, job, evidência, claim factual, risco ou relatório. Outcomes
`SUCCEEDED`, `NO_RESULTS` e `PARTIAL` são utilizáveis apenas para liberar
dependências deste mesmo mecanismo.

## Limites e riscos conhecidos

- uma interrupção depois do commit do ownership e antes da conclusão deixa o comando
  em andamento; recuperação/lease exige fase própria;
- idempotência do runner permanece em memória por instância; o ownership PostgreSQL
  evita segunda propriedade da operação, mas não é uma fila distribuída;
- não há execução paralela, paginação adicional ou `FETCH_DETAILS`;
- a versão da source policy é uma referência explícita e persistida, mas não há
  catálogo de aprovações de fontes neste corte; por isso somente o simulador
  sintético admitido pode ser usado;
- não há conector real, credencial, HTTP, rede, API, endpoint ou frontend novo;
- a conclusão redigida não pode alimentar evidência, claims ou risco.

## Critérios para revisão

- invariantes/digests e mappers falham fechado diante de adulteração;
- replay, colisão, prazo, autorização e redaction possuem testes unitários;
- PostgreSQL real cobre round-trip, tenant scope, constraints, adulteração,
  downgrade/refusal e convergência Alembic/metadata;
- lint, formatação, tipos, scanner, testes e builds passam integralmente;
- revisão independente deve decidir aceite ou exigir uma F4.6.1; implementação
  não equivale a aceite.
