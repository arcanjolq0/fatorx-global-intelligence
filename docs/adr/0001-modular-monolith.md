# ADR-0001 — Monólito modular com workers assíncronos

- Status: Accepted
- Data: 2026-07-25

## Contexto

O produto possui domínio complexo, mas ainda não tem volume, times ou SLAs que justifiquem serviços independentes. Investigações têm jobs longos e precisam sobreviver ao ciclo do request web.

## Decisão

Construir o MVP como monólito modular, com um código-base backend e entrypoints separados para API e workers. Módulos comunicam-se por casos de uso/portas e eventos internos. Jobs usam fila por adaptador, outbox/inbox e idempotência.

## Consequências

- Menos custo operacional e transações locais mais simples.
- Fronteiras precisam de testes arquiteturais para não virarem acoplamento informal.
- API e workers podem escalar separadamente.
- Extração futura de serviço depende de evidência de escala, segurança ou ownership, com candidatos naturais em documentos/browser.
