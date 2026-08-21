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
| 0015 | Accepted | controles locais de uma única operação de conector |
| 0016 | Accepted | entrada versionada, CAS e ledger durável do lifecycle inicial |
| 0017 | Accepted | matching determinístico versionado e pausa transacional para revisão humana |
| 0018 | Accepted | reconstituição canônica fail-closed das avaliações persistidas |
| 0019 | Accepted | confirmação humana, materialização determinística e replay ancorado na transição histórica |
| 0020 | Accepted | política e persistência do plano determinístico, corrigida pela F4.4.1 |
| 0021 | Accepted | ativação transacional e manifesto imutável de coleta F4.5/F4.5.1 |
| 0022 | Accepted | execução direta controlada F4.6, corrigida por F4.6.1/F4.6.2 |
| 0023 | Accepted | separação entre Gate F4-F e Gate E2E para handoff à Fase 5 |
| 0024 | Accepted | núcleo canônico de evidências F5.1 aceito após revisão independente com correções |
