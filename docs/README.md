# Documentação do projeto

## Referência e requisitos

- `project-plan.md`: transcrição normalizada do planejamento fornecido; preserva a intenção original.
- `product-requirements.md`: requisitos consolidados, escopo e invariantes do produto.
- `critical-analysis.md`: análise crítica, riscos, ambiguidades e dependências.
- `open-questions.md`: decisões comerciais, jurídicas e operacionais ainda pendentes.

## Arquitetura e contratos

- `architecture.md`: arquitetura lógica, fluxos, fronteiras e estrutura proposta.
- `data-model.md`: modelo relacional inicial e invariantes.
- `domain-foundation.md`: tipos, entidades imutáveis, invariantes e adiamentos da F2.1.
- `connector-contract.md`: porta comum para conectores e taxonomia de resultados/falhas.
- `evidence-contract.md`: proveniência, cadeia de custódia, claims e admissibilidade.
- `investigation-lifecycle.md`: estados, transições e regras de conclusão.
- `country-packs.md`: contrato para pacotes por jurisdição.
- `scoring-methodology.md`: separação entre fatos, regras de risco e interpretação.

## Qualidade, operação e conformidade

- `development.md`: instalação reproduzível, execução local, comandos e CI.
- `dependencies.md`: justificativa, manutenção, licença e alternativas das dependências diretas.
- `testing-strategy.md`: pirâmide de testes, gates e cenários críticos.
- `mvp-definition-of-done.md`: critérios mensuráveis de conclusão do MVP.
- `security.md`: modelo de ameaças e controles mínimos.
- `source-policy.md`: admissão, uso e desativação de fontes.

## Validações

- `validation/f1.2-clean-validation.md`: instalação limpa, gates locais, auditoria Git e limites da validação da Fase 1.
- `validation/f2.2-postgresql-migrations.md`: schema, migrations, constraints e gates da F2.2 validados em PostgreSQL real.

## Decisões

- `adr/README.md`: índice e regras dos registros de decisão arquitetural.
- `adr/0001-modular-monolith.md`: monólito modular com workers assíncronos.
- `adr/0002-domain-boundaries.md`: separação entre conectores, domínio e projeções.
- `adr/0003-evidence-and-claims.md`: evidência imutável e claims rastreáveis.
- `adr/0004-versioned-risk-engine.md`: risco determinístico separado de IA.
- `adr/0005-country-packs.md`: extensibilidade por pacotes de país.
- `adr/0006-investigation-state-machine.md`: máquina de estados persistida.
- `adr/0007-storage-and-search.md`: PostgreSQL como fonte de verdade e storage de objetos para artefatos.
- `adr/0008-tenancy-boundary.md`: workspace como fronteira de autorização.
- `adr/0009-application-stack.md`: stack executável e ferramentas da Fase 1.
- `adr/0010-initial-relational-persistence.md`: stack relacional, convenções e isolamento da F2.2.

## Regra de consistência

O plano de entrada registra desejos e recomendações. Requisitos consolidados e ADRs aceitos registram a decisão vigente. Se um documento mudar, atualize os links e conceitos dependentes no mesmo diff.
