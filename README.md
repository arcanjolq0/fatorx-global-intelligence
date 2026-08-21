# Fator X Global Intelligence

Plataforma de investigação empresarial internacional orientada por evidências para apoiar análise de crédito, validação de fornecedores, localização de contatos corporativos e consultas cadastrais, financeiras, societárias, jurídicas, documentais, de insolvência e de sanções.

## Estado atual

O repositório concluiu a Fase 3 e a **Fase 4 exclusivamente no Gate F4-F**, conforme o ADR 0023; o Gate E2E permanece aberto e obrigatório antes do piloto. A execução continua limitada a um `SEARCH` sintético em `TEST`. A F5.1 e o ADR 0024 foram aceitos após revisão independente com correções e materializam somente o núcleo canônico e imutável de evidências. Não há autenticação, acesso da API ao banco, jobs, filas, workers, conector real, HTTP externo, claims factuais, risco ou relatório. Subfases posteriores à F5.1 não estão autorizadas.

## Como navegar

- [PLANS.md](PLANS.md): plano de execução, dependências, gates e próxima tarefa.
- [AGENTS.md](AGENTS.md): regras obrigatórias para qualquer pessoa ou agente que altere o repositório.
- [docs/README.md](docs/README.md): índice da documentação.
- [docs/project-plan.md](docs/project-plan.md): planejamento de entrada, transcrito do documento fornecido.
- [docs/critical-analysis.md](docs/critical-analysis.md): análise crítica, riscos, ambiguidades e validações pendentes.
- [docs/development.md](docs/development.md): instalação, execução e gates locais.
- [docs/dependencies.md](docs/dependencies.md): versões, finalidade, manutenção, licenças e alternativas das dependências.
- [docs/domain-foundation.md](docs/domain-foundation.md): tipos, entidades e invariantes implementados na F2.1.
- [docs/validation/f1.2-clean-validation.md](docs/validation/f1.2-clean-validation.md): evidência da instalação e dos gates executados em ambiente limpo.
- [docs/validation/f2.2-postgresql-migrations.md](docs/validation/f2.2-postgresql-migrations.md): evidência das migrations, constraints e gates executados com PostgreSQL real.
- [docs/validation/f2.2.1-relational-hardening.md](docs/validation/f2.2.1-relational-hardening.md): evidência das guardas destrutivas, constraints temporais e imagem fixada.
- [docs/validation/f3.2-simulators-contract-suite.md](docs/validation/f3.2-simulators-contract-suite.md): evidência dos simuladores, suíte comum, cobertura e gates da F3.2.
- [docs/validation/f5.1-canonical-evidence-core.md](docs/validation/f5.1-canonical-evidence-core.md): validação e aceite independente do núcleo canônico de evidências.

As decisões aceitas em `docs/adr/` prevalecem sobre recomendações ainda não decididas no planejamento de entrada.

## Execução local

Consulte [docs/development.md](docs/development.md). O comando agregado de verificação é `pnpm quality`.

## Próximo passo

Nenhuma subfase posterior à F5.1 está autorizada. O Gate E2E continua aberto e obrigatório antes do piloto; qualquer próximo incremento depende de autorização explícita do responsável pelo projeto.
