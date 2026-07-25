# Critérios objetivos de conclusão do MVP

## 1. Regra de declaração

O produto só pode ser chamado de **MVP produtivo** quando todos os critérios obrigatórios abaixo possuírem evidência verificável e aceite nominal. Um fluxo completo apenas com conectores simulados é um **MVP técnico**, não comprova cobertura de mercado e não pode ser vendido como fonte real.

## 2. Produto e fluxo

| ID | Critério | Evidência de aceite |
|---|---|---|
| MVP-FLW-01 | Usuário autorizado cria investigação com empresa/país/identificadores e recebe ID auditável. | E2E aprovado. |
| MVP-FLW-02 | Homônimos são exibidos e coleta aprofundada fica bloqueada até confirmação. | E2E de ambiguidade. |
| MVP-FLW-03 | Capacidades são planejadas conforme perfil, país, policy, budget e deadline. | Teste de plano + snapshot. |
| MVP-FLW-04 | Pelo menos dois conectores simulados executam concorrentemente e uma falha não perde o outro resultado. | Teste de integração determinístico. |
| MVP-FLW-05 | Estados, progresso, falhas e lacunas são visíveis e auditáveis. | E2E + eventos. |
| MVP-FLW-06 | Histórico preserva investigações e versões sem reabrir terminal. | Teste de persistência. |
| MVP-FLW-07 | Analista revisa candidatos, claims críticos, conflitos e relatório conforme alçada. | E2E por papel. |

## 3. Fontes e cobertura produtiva

| ID | Critério | Evidência de aceite |
|---|---|---|
| MVP-SRC-01 | Cada fonte real ativa possui `SourcePolicyVersion` com aprovações técnica, jurídica e comercial. | Registro completo e assinado. |
| MVP-SRC-02 | Nenhuma integração contorna autenticação, pagamento, CAPTCHA, bloqueio ou termos. | Revisão de código/segurança. |
| MVP-SRC-03 | Cada conector real passa o contrato e corpus de qualidade autorizado. | Relatório de testes. |
| MVP-SRC-04 | Matriz de país/perfil declara `SUPPORTED`, `UNSUPPORTED` ou `RESTRICTED` por capacidade, sem lacuna implícita. | Matriz versionada. |
| MVP-SRC-05 | Um país só aparece como suportado após cumprir `country-packs.md`. | Gate de release. |

A exigência de os três países iniciais estarem no mesmo MVP depende de decisão comercial. Até essa decisão, nenhum deles é presumido coberto.

## 4. Evidência e veracidade

| ID | Critério | Evidência de aceite |
|---|---|---|
| MVP-EVD-01 | 100% dos claims críticos exportados possuem evidência admissível, locator, entidade confirmada e revisão exigida. | Consulta de integridade + teste negativo. |
| MVP-EVD-02 | 100% dos fatos relevantes do relatório resolvem até fonte, aquisição e trecho/original permitido. | Auditoria automática de relatório. |
| MVP-EVD-03 | Tradução/OCR/resumo preservam original e linhagem. | Testes de derivação. |
| MVP-EVD-04 | Contradições não são descartadas e aparecem no workflow/relatório. | E2E de conflito. |
| MVP-EVD-05 | Hash, imutabilidade, revogação e expurgo seguem política. | Integração + auditoria. |
| MVP-EVD-06 | Fonte que não permite retenção não tem conteúdo armazenado além do permitido. | Teste por modo de storage. |

## 5. Entidade, risco e relatório

| ID | Critério | Evidência de aceite |
|---|---|---|
| MVP-RSK-01 | Similaridade de nome isolada não confirma ocorrência crítica. | Casos homônimos/sanções. |
| MVP-RSK-02 | Mesmas entradas e metodologia produzem mesmo score, nível e regras disparadas. | Golden tests/digest. |
| MVP-RSK-03 | Modelo indisponível ou resposta diferente não altera score. | Teste de degradação. |
| MVP-RSK-04 | Qualidade/ausência de dados aparece separada de risco. | Teste + relatório. |
| MVP-RSK-05 | Não existe decisão automática de crédito ou limite definitivo. | Revisão funcional/API. |
| MVP-RSK-06 | Relatório contém escopo, instante de corte, metodologia, fontes, limitações, lacunas e aprovação. | Validação de schema/E2E. |

## 6. Documentos

| ID | Critério | Evidência de aceite |
|---|---|---|
| MVP-DOC-01 | Uploads são limitados, quarentenados e verificados antes de parsing. | Testes de segurança. |
| MVP-DOC-02 | PDF digital e fixture escaneada geram texto/evidência com página; falha é explícita. | Integração/E2E. |
| MVP-DOC-03 | Valor financeiro preserva original, moeda, unidade, período, página e conversão separada. | Unitário + fixture. |
| MVP-DOC-04 | Conteúdo incorporado nunca é executado/tratado como instrução. | Testes hostis. |

## 7. Segurança, privacidade e auditoria

| ID | Critério | Evidência de aceite |
|---|---|---|
| MVP-SEC-01 | Zero segredo real em repositório, imagem, fixture, log e relatório de teste. | Scanner + revisão. |
| MVP-SEC-02 | Suite de SSRF bloqueia todos os casos privados/loopback/link-local e redirecionamentos hostis. | Teste automatizado. |
| MVP-SEC-03 | Suite de isolamento entre workspaces e papéis passa sem exceção. | Testes negativos. |
| MVP-SEC-04 | Acesso, revisão, aprovação, exportação, política e mudança de estado geram auditoria. | Consulta de cobertura de eventos. |
| MVP-SEC-05 | Retenção/expurgo por classe e fonte foi testado, inclusive storage. | Teste de lifecycle. |
| MVP-SEC-06 | Não há achado crítico ou alto sem correção; exceção exige aceite formal, prazo e controle compensatório. | Relatório de segurança. |

## 8. Qualidade e operação

| ID | Critério | Evidência de aceite |
|---|---|---|
| MVP-OPS-01 | Tipos estritos, lint, builds e todos os testes obrigatórios passam. | Pipeline verde. |
| MVP-OPS-02 | Branch coverage dos módulos críticos >= 90% e line coverage total >= 80%. | Relatório de cobertura. |
| MVP-OPS-03 | CI comum realiza zero chamada a fonte externa real. | Teste de egress/log. |
| MVP-OPS-04 | Migrations funcionam em banco vazio e upgrade da versão anterior suportada. | Pipeline de migration. |
| MVP-OPS-05 | Retry, idempotência, outbox e retomada após interrupção foram exercitados. | Testes de falha. |
| MVP-OPS-06 | Backup e restauração recuperam metadados e artefatos dentro de objetivos aprovados. | Exercício documentado. |
| MVP-OPS-07 | SLOs numéricos de latência, throughput, prazo máximo e disponibilidade foram aprovados comercialmente e o teste de carga passa. | Documento de SLO + relatório. |
| MVP-OPS-08 | Alertas, dashboards e runbooks cobrem falha de conector, fila, storage, custo e erro interno. | Checklist operacional. |

## 9. Experiência e acessibilidade

- fluxo completo pode ser operado por teclado;
- foco e mensagens de erro são perceptíveis;
- status não depende apenas de cor;
- fonte, locator, confiança e limitações são legíveis;
- nenhum erro crítico de acessibilidade definido pelo baseline aprovado permanece;
- usuários-piloto concluem os cenários principais e o aceite é registrado.

## 10. Documentação e governança

- instalação, operação, backup, recuperação e incidentes documentados;
- contratos, ADRs, catálogo de fontes e versões atualizados;
- dependências justificadas e revisadas;
- owners de produto, risco, fontes, segurança e operação nomeados;
- perguntas bloqueadoras de `open-questions.md` resolvidas;
- release e rollback ensaiados.

## 11. Condições que impedem declarar MVP

- somente simuladores ou fonte sem aprovação;
- país exibido sem matriz de cobertura;
- claim crítico sem evidência/revisão;
- metodologia sem owner/aprovação;
- ausência de isolamento, retenção ou auditoria;
- teste crítico skipped/falho;
- SLO, custo ou licença não definidos;
- decisão automática de crédito disfarçada de recomendação.
