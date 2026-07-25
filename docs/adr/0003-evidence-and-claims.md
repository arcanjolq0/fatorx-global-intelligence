# ADR-0003 — Evidência imutável e claims rastreáveis

- Status: Accepted
- Data: 2026-07-25

## Contexto

Relatórios de crédito, sanções e jurídico exigem prova, temporalidade, entidade correta e tratamento de contradição. Um campo “fonte” em cada fato é insuficiente.

## Decisão

Separar `Artifact`, `Evidence`, `Claim` e `ClaimEvidenceLink`. Evidência é imutável e localizável; derivação cria novo registro com linhagem. Links indicam suporte, contradição ou qualificação. Claims críticos só são factuais quando passam o gate de admissibilidade e revisão.

## Consequências

- Mais registros e storage, compensados por auditoria e reprodutibilidade.
- Correções são eventos/novas versões, não updates silenciosos.
- Relatórios podem ser auditados até o original.
- Política de fonte controla se original, trecho ou somente referência pode ser retido/exibido.
