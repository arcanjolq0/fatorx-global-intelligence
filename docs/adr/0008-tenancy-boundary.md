# ADR-0008 — Workspace como fronteira de autorização

- Status: Accepted
- Data: 2026-07-25

## Contexto

O modelo comercial ainda não esclarece se haverá clientes externos, mas adicionar isolamento depois afetaria schema, cache, storage, fila e auditoria.

## Decisão

Toda raiz agregada pertence a `workspace_id`; banco, storage, cache, jobs e autorização carregam essa chave. O MVP pode operar com um único workspace Fator X, sem presumir SaaS público. Papéis iniciais são analista, revisor, administrador e auditor.

## Consequências

- Evita redesign estrutural se houver múltiplos clientes.
- Exige testes sistemáticos de isolamento mesmo no workspace único.
- Não decide faturamento, self-service nem isolamento físico.
- Modelo comercial e SSO continuam pendentes.
