# F5.1 — Núcleo canônico de evidências

## Status

**IMPLEMENTADA — AGUARDANDO REVISÃO INDEPENDENTE.** Não promovida e sem
checkpoint final.

## Objetivo

Materializar a primeira fronteira factual do produto: evidência tenant-scoped,
imutável, localizável e ligada à decisão humana de identidade, sem criar claims
ou capacidades operacionais posteriores.

## Entregas

- `Artifact` com proveniência, hash original, origem, fonte/política, tempo e
  políticas tipadas;
- `Evidence` versionada, sempre `PENDING`, com locator tipado e hash do trecho;
- `EvidenceLifecycleEvent` append-only para supersessão e revogação;
- validação integral de `EvidenceHistory` e reconstituição fail-closed;
- comandos idempotentes de registro, correção, revogação e leitura;
- serialização de correção/revogação concorrentes pela versão-alvo;
- autorização por função, tenancy e auditoria redigida;
- porta de evidência, adapter PostgreSQL e migration `20260814_11`;
- testes unitários, PostgreSQL, migration, tenancy, imutabilidade e adulteração.

## Critérios de aceitação

1. Bytes alterados mudam hashes e adulteração persistida falha fechado.
2. Artefato, decisão, Company e Investigation permanecem no mesmo workspace.
3. Todos os locators mínimos fazem round-trip canônico.
4. Correção não altera linha anterior nem artefato e cria evento correspondente.
5. Revogação é terminal, append-only e restrita a admin/owner.
6. Replay igual é idempotente; reutilização divergente do comando falha.
7. Não existem update/delete nas portas e downgrade recusa apagar histórico.
8. Não há I/O externo, fonte real, claim, risco, IA, job ou interface.
9. Vínculos de série/evento não atravessam tenant e mutações concorrentes não
   produzem histórico contraditório.

## Limitações deliberadas

- object storage, catálogo de fontes e `ConnectorRun` ainda não existem;
- nenhum modo de storage realiza gravação de objeto nesta subfase;
- somente corpus sintético/controlado pode ser usado;
- admissibilidade permanece `PENDING`;
- derivação, expiração, redação e expurgo serão decisões posteriores;
- Gate E2E continua aberto antes do piloto.

## Gate

Somente parecer independente `ACEITAR` permite aceitar o ADR 0024, promover a
F5.1 e criar o checkpoint final. Qualquer achado material exige correção e nova
revisão.
