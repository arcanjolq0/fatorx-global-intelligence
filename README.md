# Fator X Global Intelligence

Plataforma de investigação empresarial internacional orientada por evidências para apoiar análise de crédito, validação de fornecedores, localização de contatos corporativos e consultas cadastrais, financeiras, societárias, jurídicas, documentais, de insolvência e de sanções.

## Estado atual

O repositório concluiu a Fase 3; F4.1 a F4.5/F4.5.1 foram aceitas após revisão independente. A F4.5/F4.5.1 revalida o prazo, ativa um plano `READY`, persiste run/operações imutáveis e avança somente `PLANNING -> COLLECTING`, sem executar conectores. Permanecem a API FastAPI somente com `GET /health`, o shell React/Vite estático e conectores simulados sem I/O externo. Não há autenticação, acesso da API ao banco, execução do manifesto, jobs, filas, workers, vínculo com Company existente, conector real ou integração externa. **F4.6 — NÃO AUTORIZADA** e a Fase 4 permanece em andamento.

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

As decisões aceitas em `docs/adr/` prevalecem sobre recomendações ainda não decididas no planejamento de entrada.

## Execução local

Consulte [docs/development.md](docs/development.md). O comando agregado de verificação é `pnpm quality`.

## Próximo passo

A F2.2.1 está concluída. Não iniciar a F2.3 nem antecipar repositórios, acesso da API ao banco ou transições sem nova instrução; o próximo incremento deve respeitar os gates e as dependências comerciais de `PLANS.md`.
