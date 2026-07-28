# Registros de decisão arquitetural

## Convenção

Cada ADR registra contexto, decisão, consequências e status. Status possíveis: `Proposed`, `Accepted`, `Superseded`, `Rejected`.

- ADR aceito não é reescrito para mudar a decisão; crie novo ADR e marque o anterior como substituído.
- Correções editoriais sem mudança semântica são permitidas.
- Mudanças de contratos centrais, persistência, segurança, risco, tenancy ou topologia exigem ADR.

## Índice

| ADR | Status | Decisão |
|---|---|---|
| 0001 | Accepted | monólito modular com workers assíncronos |
| 0002 | Accepted | fronteiras entre conectores, domínio e projeções |
| 0003 | Accepted | evidência imutável separada de claims |
| 0004 | Accepted | motor de risco determinístico e versionado |
| 0005 | Accepted | extensão por pacotes versionados de país |
| 0006 | Accepted | máquina de estados persistida e idempotente |
| 0007 | Accepted | PostgreSQL + storage de objetos; busca especializada adiada |
| 0008 | Accepted | workspace como fronteira obrigatória de autorização |
| 0009 | Accepted | Python/FastAPI e React/TypeScript/Vite para a fundação executável |
| 0010 | Accepted | SQLAlchemy Core síncrono, Alembic e isolamento relacional inicial |
| 0011 | Accepted | portas, repositórios Core, Unit of Work e reconstituição de snapshots |
| 0012 | Accepted | identidades internas, membership única por workspace e auditoria append-only |
| 0013 | Accepted | contexto do ator, autorização por papel, último owner e auditoria coordenada |
| 0014 | Accepted | contratos versionados de conectores, cobertura e registro explícitos |
