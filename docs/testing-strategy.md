# Estratégia de testes

## 1. Objetivos

Os testes devem demonstrar correção do domínio, rastreabilidade, isolamento, tolerância a falhas e reprodutibilidade. Cobertura numérica é um sinal, não substituto de cenários críticos.

## 2. Regras gerais

- CI não acessa internet nem fontes reais.
- Fixtures são sintéticas ou legalmente autorizadas, redigidas e versionadas.
- Segredos, tokens, cookies e payloads licenciados não entram em snapshot.
- Tempo, UUID, moeda, rede e modelos são injetáveis/controláveis nos testes.
- Testes de domínio são determinísticos e independem de banco/fila.
- Falha nunca é ocultada com retry infinito, skip genérico ou asserção enfraquecida.
- Cada bug crítico recebe teste de regressão.

## 3. Camadas

### 3.1 Testes unitários

Alvos:

- valores e invariantes;
- normalização de nomes, identificadores, endereços e domínios;
- resolução de entidades por dimensão;
- admissibilidade e cadeia de evidência;
- claims, conflitos e revisão;
- regras de risco, Decimal, datas e validade;
- máquina de estados e idempotência;
- políticas de país e fonte.

Sem I/O, rede ou framework web.

### 3.2 Testes de contrato

Uma suíte reutilizável valida todo conector e pacote de país. Para conectores, cobre descritor, schemas, deadlines, cancelamento, paginação, budget, erros, idempotência, política e ausência de vazamento. Para pacotes, cobre manifesto, normalização e compatibilidade.

### 3.3 Testes de integração

Usam serviços locais efêmeros/controlados:

- PostgreSQL e migrations;
- adaptador de fila/outbox/inbox;
- storage de objetos e expurgo;
- API e autorização;
- servidor HTTP simulado para redirecionamentos, timeouts e payloads;
- pipeline documental com fixtures;
- persistência de relatório e auditoria.

Não usam conta ou endpoint de fornecedor.

Desde a F2.2, os testes relacionais usam exclusivamente PostgreSQL 18.4 real. Cada cenário destrutivo retorna as revisions à `base`, aplica `head` quando necessário e encerra novamente em `base`, evitando dependência de ordem. Antes de criar engine, abrir conexão ou chamar Alembic, a guarda exige simultaneamente `FATORX_ALLOW_DESTRUCTIVE_DATABASE_TESTS=1`, host `localhost`, `127.0.0.1` ou `::1` e banco `fatorx_test` ou `fatorx_test_<sufixo seguro>`. Query string e variáveis libpq que podem redirecionar o alvo são proibidas; `PGOPTIONS` também é rejeitada para impedir alteração de `search_path`. São verificados tipos, PKs, FKs, checks, índices, isolamento composto por workspace, coerência de estado/timestamps — inclusive cancelamento direto atômico —, upgrade repetido, downgrade e aderência entre metadata e migration. SQLite e mocks de PostgreSQL são proibidos.

Na F2.3, testes unitários exercitam mapeadores válidos/inválidos, tipos fortes, `Decimal`, UTC, reconstituição e ciclo básico da Unit of Work com doubles controlados. Testes PostgreSQL reais comprovam `INSERT -> COMMIT -> SELECT` para as três entidades, todos os status aplicáveis, snapshots não iniciais e terminais, rollback padrão/em exceção, transação compartilhada, conflitos traduzidos e consultas isoladas por workspace. Um teste arquitetural por AST impede commit dentro dos repositórios e conexão durante import.

Na F2.3.1, o guard transacional é testado contra conexão fechada, transação original inativa e identidade diferente em `connection.get_transaction()`. Testes PostgreSQL reais capturam repositórios antes de commit/rollback, tentam leitura e escrita depois do encerramento e confirmam que nenhuma nova transação aparece por autobegin. Doubles controlados provocam falhas SQLAlchemy de início, commit e rollback para validar tradução e mensagens públicas redigidas; esses doubles complementam, sem substituir, os testes PostgreSQL reais.

Na F2.3.2, os doubles mantêm deliberadamente a `RootTransaction` ativa e sua identidade preservada depois de falhas de commit/rollback. A suíte exige invalidação explícita do guard, bloqueio de leitura/escrita e de toda nova finalização pública, tentativa de limpeza interna pelo `__exit__`, não reutilização depois de falha de entrada e terminalidade mesmo quando o fechamento falha. SQL, URL, senha e marcadores técnicos são inseridos apenas nas exceções simuladas e devem permanecer ausentes das mensagens públicas. Os testes PostgreSQL reais continuam cobrindo falhas efetivas de início, commit e rollback, operações normais e ausência de autobegin após finalizações bem-sucedidas.

Na F2.4.1, testes unitários cobrem e-mail canônico, identidades, memberships, auditoria imutável, IDs fortes e mapeadores. PostgreSQL real comprova a nova revision a partir de banco vazio e da revision anterior — inclusive com `requested_by` órfão preservado —, constraints, downgrade de uma revision, re-upgrade e round-trip dos três novos snapshots. Os testes transacionais exigem o mesmo guard nos seis repositórios, rollback sem dados parciais, bloqueio depois de finalização/falha e nenhuma transação por autobegin.

Na F2.4.2, uma tabela unitária exaustiva cobre cada combinação de quatro papéis e oito permissões. Fakes com estado transacional exercitam autorizador e serviços sem simular PostgreSQL. Integração real comprova escopo exclusivo do ator, `requested_by`, auditoria atômica, negações persistidas, falhas sem sucesso, locks da membership e terminalidade do guard. Corridas usam `Barrier`, `Event`, threads daemon, `lock_timeout` local e join limitado; sleeps arbitrários não são o mecanismo de sincronização.

Na F3.1, testes unitários cobrem IDs fortes, SemVer, cobertura explícita,
contexto sem segredo, queries, candidatos opacos, escalares de observação,
artefatos, metadados, todos os estados de outcome, Protocol e seleção do
registry. Testes AST impedem imports de aplicação/infraestrutura/frameworks,
rede, banco, filesystem, descoberta dinâmica, simuladores e migrations novas.
A suíte focada executa com sockets desabilitados e exige pelo menos 90% de
branch coverage em `intelligence.connectors`.

Na F3.2, uma suíte comum recebe factory, entradas sintéticas e expectativas
tipadas, sem conhecer detalhes internos do conector. Ela compara execuções na
mesma instância e em instâncias novas, valida tipos por operação, proveniência,
status, imutabilidade e descritor estável. Doubles incompatíveis apenas nos
testes provam rejeição de tipos incorretos, IDs divergentes, fonte divergente,
não determinismo, descritor mutante e operação não declarada. Os onze cenários
do registro empresarial usam somente valores fixos; AST bloqueia rede,
filesystem, ambiente, subprocesso, relógio, aleatoriedade, importação dinâmica
e, naquela entrega, componentes ainda não autorizados de F3.3. Sockets continuam
desabilitados na suíte focada.

Na F3.3, testes de um runner de operação única usam relógio, sleeper, jitter,
sinal de cancelamento, conector e idempotência controlados. `asyncio.Event`
sincroniza timeout, cancelamento e replay concorrente; sleeps arbitrários são
proibidos por AST. A suíte cobre preflight com zero chamadas/esperas, as três
operações, retry e `retry_after`, budget entre tentativas, fingerprint/digest,
replay de sucesso/falha, corrida com exatamente uma chamada, colisão, liberação
de owner cancelado, uma página, truncamento e outcomes incompatíveis. A área
`intelligence.connectors.execution` exige pelo menos 90% de branch coverage,
com sockets bloqueados salvo o loopback interno necessário ao event loop do
Windows; nenhum teste ou código abre conexão de rede.

Na F4.1, unitários exercitam o envelope de identificação, operações puras,
comandos, matriz de autorização, erros, clock, replay, colisão e rollback em
cada estágio coordenado. PostgreSQL real comprova JSONB canônico, CAS correto e
desatualizado, isolamento/FK tenant-scoped, unique de comando, replay após novo
UoW, rollback integral e migration reversível. Corridas usam `Barrier` e duas
transações reais, sem `sleep`: comandos distintos na mesma versão deixam um
único vencedor; o mesmo comando deixa um efeito e um replay. Guardas AST
bloqueiam runner F3.3, I/O, ambiente, API genérica de transição, pacote de fase
posterior, mutação do ledger e snapshot na auditoria.

Na F4.2, unitários cobrem contratos/schemas fechados, normalização Unicode, sete
dimensões, pesos, thresholds, conflitos fortes, score/cobertura inteiros,
ranking estável, redaction, autorização, replay/collision e falhas coordenadas.
PostgreSQL real comprova três tabelas tenant-scoped, round-trip da política,
identidade/origem e dimensões, CAS, ausência de órfãos, rollback e migration
reversível. Duas corridas com `Barrier` provam um vencedor para comandos
distintos e um efeito/replay para o mesmo comando. Guardas AST bloqueiam float,
I/O/conector, criação de Company, transição a `PLANNING` e mutação de candidatos.
`entity_resolution` exige ao menos 95% e a aplicação/persistência específica da
F4.2 ao menos 90% de branch coverage.

Na F4.2.1, testes de integridade alteram valores ainda formalmente válidos e
exigem rejeição semântica de total, cobertura, classificação, conflito,
dimensão, peso, score, contribuição, disponibilidade, explicação, digests,
contexto e ranking. Testes PostgreSQL modificam diretamente batch, candidato,
snapshot e dimensão em transações controladas, carregam pelo repositório e
restauram a linha em `finally`. Normalizações diferentes de
`NAME_NORMALIZATION_V1` são rejeitadas. A suíte também preserva round-trip,
tenant isolation, replay, concorrência, rollback e migrations da F4.2.

Na F4.3, unitários cobrem política/digest de materialização, todos os status,
invariantes da Investigation, permissão, motivos/override, bloqueio de
`EXCLUDED`, replay sem relógio, collision, CAS e rollback por estágio. Testes
PostgreSQL cobrem a tabela append-only, FKs/unique tenant-scoped, round-trip,
adulteração de decisão/Company/política, concorrência e downgrade que recusa
`UNKNOWN`. Guardas arquiteturais proíbem confirmação automática, mutação do
candidato, planner, plano, I/O, ambiente, subprocesso e escopos posteriores.
Materialização exige 95%; serviço e persistência F4.3 exigem 90% de branch
coverage.

Na F4.4, unitários cobrem política/digests, ordenação país/global, capacidades
required/optional, grafo, orçamento/deadline, autorização, replay sem relógio ou
IDs, colisão e rollback por estágio. PostgreSQL real cobre as três tabelas,
round-trip completo, tenant isolation, adulteração, concorrência sem sleeps,
ausência de mudança em estado/versão e migration reversível/fail-safe. Guardas
arquiteturais mantêm planejamento puro e proíbem execução de conectores, HTTP,
jobs, filas, workers e transição a `COLLECTING`.

Na F4.4.1, unitários e PostgreSQL cobrem os dez estados de continuidade, versão
maior/menor, estados anteriores, troca de Company, lote ativo reintroduzido e as
três chaves de leitura. O deadline é testado com opcionais indisponíveis, sem
sleep. A migration sucessora testa combinações parciais de custo, conjuntos
tipados válidos, upgrade, downgrade e convergência do metadata.

Na F4.5, unitários cobrem política/digests, rank 1, opcionais indisponíveis,
dependências, grafo, contexto, lifecycle, autorização, replay sem clock/IDs/CAS,
collision e rollback em cada estágio. PostgreSQL real cobre round-trip das três
tabelas, isolamento tenant, adulteração, concorrência sem sleeps, unicidades e
migration upgrade/downgrade/refusal/check. A guarda arquitetural proíbe imports
ou chamadas de registry, simuladores, runner e mecanismos operacionais.

Na F4.5.1, unitários e PostgreSQL real cobrem prazo suficiente, insuficiente e
exatamente no limite, sempre com caminho crítico formado somente por operações
`READY`. As três leituras validam o par run/transição; ausência de qualquer lado
e divergência de ator, instante, run, Company, plano, política ou contagem falham
fechado. Replay em nova UoW e colisão verdadeira continuam separados. A
migration sucessora cobre backfill, FK composta, upgrade, downgrade e
`alembic check`; o ZIP é validado por nomes POSIX e `unzip -t`.

Na F4.6, unitários cobrem comando/política/digests, autorização, prazo, replay
sem clock/conector/escrita, colisão e ausência de payload persistido. PostgreSQL
real cobre ownership pré-I/O, conclusão 1:1, tenant scope, round-trip dos mappers,
adulteração fail-closed, constraints, downgrade/refusal e convergência do
metadata. Somente o simulador admitido em `TEST` participa; rede e fontes reais
continuam proibidas.

Na F4.6.1, um conector adversarial muda o descritor entre os preflights e deve
ser rejeitado antes de `search`. A corrida F4.3 de comandos distintos deve
produzir um sucesso e um `STATE_VERSION_CONFLICT` auditado em cinco repetições,
sem contagem dependente do escalonamento.

Na F4.6.2, a mesma continuidade é testada após a primeira tentativa com
`INVALID_RESPONSE` configurado como retriável. A divergência deve produzir no
máximo uma chamada de operação e nunca iniciar novo I/O.

Na F5.1, unitários cobrem hashes, políticas tipadas, os sete locators canônicos,
discriminadores fechados, JSON Pointer RFC 6901, redaction, série contígua,
supersessão, revogação, replay/collision, permissões e auditoria dos caminhos de
falha. PostgreSQL real cobre round-trip, FKs tenant-scoped, reconstituição
fail-closed, adulteração, concorrência correção×revogação, migration e recusa de
downgrade destrutivo. Histórias novas ou corrigidas são validadas integralmente
antes do primeiro append; regressões devem provar que uma história inválida não
deixa artefato, versão ou evento parcial.

### 3.4 Testes de segurança

- SSRF: loopback, RFC1918, link-local, IPv6, DNS rebinding simulado e cadeia de redirects;
- upload: tipo falso, arquivo excessivo, arquivo comprimido hostil, macro/script e conteúdo corrompido;
- autorização: acesso horizontal/vertical e troca de workspace;
- prompt injection: instruções em HTML/PDF/JSON não mudam ferramenta, política ou score;
- secrets: scanner, logs e mensagens de erro;
- XSS/sanitização de conteúdo e relatório;
- rate limit, budget e payload excessivo;
- corrida/idempotência e replay.

O filtro relacional e a consulta tenant-first de membership continuam testados separadamente. A F2.4.2 testa autorização por papel, contexto do ator e auditoria coordenada no nível dos serviços, sem transferir regras de acesso aos testes ou adaptadores de repositório.

### 3.5 Testes ponta a ponta

Executados com conectores simulados determinísticos:

1. empresa única com identificador forte e relatório completo;
2. empresas homônimas exigindo confirmação;
3. fonte indisponível e conclusão parcial;
4. `NO_RESULTS` sem marcar falha;
5. processo pertencente a homônimo rejeitado;
6. possível sanção por nome semelhante bloqueada para revisão;
7. valores financeiros em moedas/unidades/períodos distintos;
8. documento escaneado e evidência localizada;
9. evidências contraditórias;
10. cancelamento com resposta tardia;
11. revisão que altera inputs e recalcula avaliação;
12. tentativa de acesso entre workspaces negada e auditada.

### 3.6 Testes de operação

- carga e concorrência contra SLO aprovado;
- worker interrompido e retomado;
- fila indisponível e reconciliação de outbox;
- backup e restauração;
- migração de versão anterior;
- storage indisponível e expurgo;
- degradação do modelo sem alteração do score.

## 4. Matriz de rastreabilidade

Cada teste crítico usa ID e referencia requisito/critério, por exemplo:

```text
REQ: RF-05
MVP: MVP-EVD-01
TEST: test_critical_claim_requires_admissible_evidence
```

A matriz pode ser gerada posteriormente, mas os identificadores devem existir desde a primeira implementação.

## 5. Gates automatizados

Quando a ferramenta for escolhida na Fase 1, o pipeline deve executar:

1. verificação de formatação;
2. lint;
3. verificação estrita de tipos;
4. unitários e contrato;
5. integração;
6. segurança rápida;
7. scanner de segredos e dependências;
8. build de API/web;
9. E2E em pipeline adequado.

Ordem pode otimizar feedback, sem remover gates.

## 6. Metas de cobertura

- módulos críticos (`evidence`, `claims`, `risk`, `entity_resolution`, lifecycle/orchestration e contrato de conectores): pelo menos 90% de branch coverage;
- total do código de aplicação: pelo menos 80% de line coverage;
- 100% das transições e invariantes críticas exercitadas;
- código gerado, migrations declarativas e fixtures podem ser excluídos apenas por configuração justificada.

Não adicionar linhas irrelevantes para elevar cobertura; revisão de cenários tem precedência.

## 7. Fixtures

- diretório por contrato/versão e país;
- licença/proveniência da fixture documentada;
- dados pessoais substituídos por exemplos sintéticos;
- raw + expected normalized + expected evidence/claims;
- casos UTF-8, diacríticos, RTL quando suportado, datas e números locais;
- payloads hostis isolados e rotulados;
- snapshots focados em schema/semântica, não respostas integrais voláteis.

## 8. Testes de conectores reais

Após G6, executar fora da CI comum em ambiente autorizado:

- smoke test com conta de teste;
- qualidade em corpus permitido;
- limites e custo;
- retenção/exibição;
- mudança de schema e alertas.

Resultados devem ser sanitizados. Falha de teste real desabilita feature flag quando compromete integridade; não leva credencial para repositório.

## 9. Critério de falha

São bloqueadores: teste crítico falho ou skipped sem aceite, type error, migration inválida, segredo detectado, acesso externo inesperado, regressão de isolamento, claim crítico publicável sem evidência ou score alterado por modelo.

## 10. Revisão manual complementar

Antes do piloto, analistas devem revisar corpus representativo autorizado de identidade, sanções, jurídico, finanças, documentos e relatórios. Métricas e tamanho da amostra dependem do perfil comercial e serão registrados no plano de validação.
