# ADR-0004 — Risco determinístico separado de IA

- Status: Accepted
- Data: 2026-07-25

## Contexto

Modelos são úteis para extração e explicação, mas são não determinísticos e não devem controlar decisão de crédito ou regras.

## Decisão

O motor de risco avalia claims elegíveis por metodologia e regras imutáveis/versionadas. Registra snapshot/digest de entradas e cada regra disparada. IA pode produzir explicação validada a partir do resultado, com fallback por template, sem alterar score.

## Consequências

- Resultados são reproduzíveis e comparáveis por versão.
- Alterar metodologia cria versão e nova avaliação.
- Qualidade de dados é dimensão separada do risco.
- Limite de crédito definitivo fica fora do MVP até validação estatística e aprovação.
