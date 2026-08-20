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
- `validation/f2.2.1-relational-hardening.md`: consentimento destrutivo, coerência de timestamps e pin da imagem PostgreSQL validados antes da F2.3.
- `validation/f3.1-connector-contracts-registry.md`: contratos versionados, registro explícito, testes, gates e limites da F3.1.
- `validation/f3.2-simulators-contract-suite.md`: simuladores determinísticos, suíte comum, cobertura, gates e limites da F3.2.
- `validation/f3.3-connector-execution-controls.md`: controles de uma operação, corridas determinísticas, cobertura, gates e limites da F3.3.
- `validation/f4.1-investigation-lifecycle-foundation.md`: CAS, replay durável, concorrência PostgreSQL, migrations, cobertura e limites da F4.1.
- `validation/f4.2-entity-candidate-review-foundation.md`: matching determinístico, persistência tenant-scoped, concorrência, migration e limites da F4.2.
- `validation/f4.2.1-persisted-evaluation-integrity.md`: reconstrução canônica, testes de adulteração e gates da correção F4.2.1.
- `validation/f4.3-entity-confirmation-and-company-materialization.md`: confirmação humana, Company canônica, replay, migration e limites da F4.3.
- `validation/f4.3.1-durable-confirmation-replay.md`: separação entre fato histórico e estado atual, replay após avanço/cancelamento e classificação fail-closed.
- `validation/f4.4-investigation-plan.md`: política determinística, persistência, replay, concorrência, migration e limites da F4.4.
- `validation/f4.5-collection-activation-manifest.md`: ativação, manifesto, replay, atomicidade e limites da F4.5.
- `validation/f4.5.1-collection-activation-integrity.md`: revalidação de prazo, vínculo histórico exato e pacote portátil da F4.5.1.
- `validation/f4.6-direct-controlled-execution.md`: execução direta `SEARCH`, ownership pré-I/O, conclusão redigida e limites da F4.6.
- `validation/f4.6.1-descriptor-audit-continuity.md`: continuidade do descritor e auditoria concorrente corretiva.
- `validation/f4.6.2-terminal-descriptor-divergence.md`: interrupção terminal de retries após divergência do descritor.
- `validation/f4-gate-foundation-acceptance.md`: aceite explícito da Fase 4 somente no Gate F4-F e limites do Gate E2E.
- `validation/f4.4.1-plan-continuity.md`: continuidade histórica, caminho crítico executável e constraint de custo corrigida.
- `validation/f5.1-canonical-evidence-core.md`: cadeia de custódia, tenancy, concorrência, migration e gates da F5.1 ainda não promovida.

## Tarefas da Fase 5

- `tasks/f5/F5_1_NUCLEO_CANONICO_EVIDENCIAS.md`: implementação limitada do núcleo canônico de evidências, aguardando revisão independente.

## Tarefas da Fase 3

- `tasks/f3/F3_ROADMAP.md`: contexto da decomposição da Fase 3; não autoriza execução integral.
- `tasks/f3/F3_1_CONTRATOS_E_REGISTRO.md`: escopo executado exclusivamente na F3.1.
- `tasks/f3/F3_2_SIMULADORES_E_SUITE_DE_CONTRATO.md`: escopo autorizado exclusivamente na F3.2.
- `tasks/f3/F3_3_CONTROLES_DE_EXECUCAO.md`: escopo aceito da F3.3, após revisão independente, que concluiu o gate G3 e a Fase 3.

## Tarefas da Fase 4

- `tasks/f4/F4_ROADMAP.md`: decomposição da Fase 4; F4.6/F4.6.1/F4.6.2 aceitas após revisão independente.
- `tasks/f4/F4_GATE_REVIEW_AND_F5_HANDOFF.md`: parecer do gate, matriz de lacunas e plano de handoff sem autorizar a F5.
- `tasks/f4/F4_1_LIFECYCLE_TRANSACIONAL_INICIAL.md`: escopo, contratos, persistência e exclusões da F4.1.
- `tasks/f4/F4_2_CANDIDATOS_MATCHING_CONFIRMACAO.md`: escopo, política, transação e exclusões da F4.2.
- `tasks/f4/F4_2_1_CORRECAO_INTEGRIDADE_RECONSTITUICAO.md`: causa, algoritmo e limites da correção de integridade F4.2.1.
- `tasks/f4/F4_3_CONFIRMACAO_ENTIDADE_CANONICA.md`: comando humano, materialização, decisão e exclusões da F4.3.
- `tasks/f4/F4_3_1_REPLAY_HISTORICO_CONFIRMACAO.md`: correção do replay histórico durável sem efeitos colaterais.
- `tasks/f4/F4_4_PLANO_INVESTIGACAO.md`: política, plano imutável, persistência e exclusões da F4.4.
- `tasks/f4/F4_4_1_CORRECAO_CONTINUIDADE_PLANO.md`: correção curta da continuidade, prazo e auditoria da F4.4.
- `tasks/f4/F4_5_ATIVACAO_MANIFESTO_COLETA.md`: ativação transacional e manifesto persistente sem execução.
- `tasks/f4/F4_5_1_CORRECAO_PRAZO_E_INTEGRIDADE.md`: correção curta de prazo, integridade histórica e empacotamento.
- `tasks/f4/F4_6_EXECUCAO_DIRETA_CONTROLADA.md`: ownership pré-I/O e conclusão operacional redigida de um `SEARCH` em `TEST`.
- `tasks/f4/F4_6_1_CORRECAO_CONTINUIDADE_DESCRITOR_AUDITORIA.md`: correção do descritor mutável e da corrida de auditoria.
- `tasks/f4/F4_6_2_DIVERGENCIA_TERMINAL_DESCRITOR.md`: correção terminal da continuidade após uma tentativa.

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
- `adr/0011-repositories-unit-of-work-and-reconstitution.md`: portas, repositórios Core, Unit of Work e reconstituição.
- `adr/0012-internal-identities-memberships-and-audit.md`: identidades internas, memberships e auditoria append-only.
- `adr/0013-service-authorization-and-coordinated-audit.md`: contexto do ator, autorização, último owner e auditoria coordenada.
- `adr/0014-connector-contracts-and-explicit-registry.md`: contrato `1.0.0`, cobertura e registro explícitos.
- `adr/0015-single-connector-operation-execution-controls.md`: deadline, retry, budget e idempotência locais para uma operação.
- `adr/0016-transactional-investigation-lifecycle-foundation.md`: comandos fechados, CAS, idempotência durável, ledger e auditoria transacional da F4.1.
- `adr/0017-entity-candidate-matching-and-review-pause.md`: política V1, matching determinístico, candidatos append-only e pausa para revisão.
- `adr/0018-persisted-matching-evaluation-integrity.md`: reconstituição oficial fail-closed e digest de submissão independente da ordem incidental.
- `adr/0019-human-entity-confirmation-and-company-materialization.md`: confirmação exclusivamente humana, nova Company, decisão append-only e atomicidade.
- `adr/0020-deterministic-investigation-plan.md`: política pura, descritores estáticos e persistência imutável do plano F4.4.
- `adr/0021-collection-activation-manifest.md`: seleção rank 1, lifecycle e persistência imutável do manifesto F4.5.
- `adr/0022-direct-controlled-collection-execution.md`: execução direta controlada e recibo redigido da F4.6.
- `adr/0023-phase-4-gate-and-phase-5-handoff.md`: decisão aceita que separa o Gate F4-F do Gate E2E antes da Fase 5.
- `adr/0024-canonical-evidence-core.md`: decisão proposta da F5.1 sobre artefato, evidência versionada e lifecycle append-only.

## Regra de consistência

O plano de entrada registra desejos e recomendações. Requisitos consolidados e ADRs aceitos registram a decisão vigente. Se um documento mudar, atualize os links e conceitos dependentes no mesmo diff.
