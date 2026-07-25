# ADR-0007 — PostgreSQL como fonte de verdade e objetos para artefatos

- Status: Accepted
- Data: 2026-07-25

## Contexto

O plano cita PostgreSQL, pgvector, Redis, storage S3 e OpenSearch. Adotar todos antes de medir criaria custo e múltiplas fontes de verdade.

## Decisão

Usar PostgreSQL como fonte de verdade para estado e metadados. Artefatos grandes ficam em storage compatível com objetos quando a política permitir. Busca textual começa no PostgreSQL. pgvector e OpenSearch são adiados até caso e volume medidos. Fila/cache exigem decisão de implementação separada.

## Consequências

- Menos dependências iniciais e consistência mais simples.
- Storage deve usar chaves por workspace e acesso autorizado.
- Busca pode exigir evolução futura, guiada por métricas.
- Digest e metadados relacionam objetos ao banco sem transformá-lo em blob store.
