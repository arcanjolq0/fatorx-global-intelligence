# F4.5 — Ativação do plano e manifesto de coleta

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE, INCLUINDO A F4.5.1.** A Fase 4
permanece em andamento. A F4.6 foi posteriormente autorizada e implementada,
mas ainda aguarda sua própria revisão independente.

## Escopo implementado

- comando `StartInvestigationCollection`, ator obtido de `ActorContext` e
  política `COLLECTION_ACTIVATION_V1`;
- seleção exclusiva do snapshot rank 1 de cada capacidade `READY`;
- `CollectionRun` e `CollectionOperation` imutáveis, versionados e com digests;
- dependências convertidas para IDs de operações do mesmo run;
- persistência tenant-scoped em três tabelas append-only;
- transição explícita `PLANNING -> COLLECTING`, CAS e ledger correlacionado;
- autorização OWNER/ADMIN/ANALYST, auditoria mínima e replay sem efeitos;
- migration `20260802_08`, sucessora reversível de `20260801_07`.

A correção F4.5.1 revalida o prazo no instante da ativação e ancora cada run na
transição histórica exata, com Company e plano persistidos pela migration
`20260802_09`. O contrato completo está em
`F4_5_1_CORRECAO_PRAZO_E_INTEGRIDADE.md`.

## Invariantes

O plano precisa estar íntegro e `READY`, pertencer ao mesmo workspace,
Investigation e Company e ter versão de criação não superior à versão atual.
Cada capacidade `READY` tem exatamente uma opção rank 1. Dependências devem
apontar para operações do mesmo run e formar grafo acíclico. Não pode haver
outro run da Investigation ou do plano.

Run e operações começam em `PENDING`; tentativa começa em zero. Orçamento,
deadline, custos e duração vêm exclusivamente do plano persistido. O cliente
não escolhe conector, IDs internos, status, custo ou estado destino.

## Atomicidade e replay

Run, operações, dependências, CAS, ledger e auditoria compartilham um commit.
Falha em qualquer estágio reverte o conjunto. Mesmo comando/digest devolve o
mesmo manifesto sem clock, IDs, CAS ou nova auditoria. Conteúdo diferente sob o
mesmo `command_id` é colisão.

## Fora do escopo

Não há chamada de conector ou simulador, runner F3.3, retry, timeout operacional,
paralelismo, resultados, jobs, filas, workers, scheduler, outbox, HTTP, API,
frontend, evidências, claims, risco ou relatórios. Não houve dependência nem
lockfile novo.
