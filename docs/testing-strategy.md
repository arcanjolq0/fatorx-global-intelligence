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

Na F2.2, os testes relacionais usam exclusivamente PostgreSQL 18.4 real. Cada cenário retorna as revisions à `base`, aplica `head` quando necessário e encerra novamente em `base`, evitando dependência de ordem. A configuração recusa host não local ou banco cujo nome não contenha `test`. São verificados tipos, PKs, FKs, checks, índices, isolamento composto por workspace, upgrade repetido, downgrade e aderência entre metadata e migration. SQLite e mocks de PostgreSQL são proibidos.

### 3.4 Testes de segurança

- SSRF: loopback, RFC1918, link-local, IPv6, DNS rebinding simulado e cadeia de redirects;
- upload: tipo falso, arquivo excessivo, arquivo comprimido hostil, macro/script e conteúdo corrompido;
- autorização: acesso horizontal/vertical e troca de workspace;
- prompt injection: instruções em HTML/PDF/JSON não mudam ferramenta, política ou score;
- secrets: scanner, logs e mensagens de erro;
- XSS/sanitização de conteúdo e relatório;
- rate limit, budget e payload excessivo;
- corrida/idempotência e replay.

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

- módulos críticos (`evidence`, `claims`, `risk`, `entity_resolution`, `orchestration` e contrato de conectores): pelo menos 90% de branch coverage;
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
