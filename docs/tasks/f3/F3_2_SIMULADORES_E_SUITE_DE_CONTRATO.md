# F3.2 — Simuladores determinísticos e suíte reutilizável de contrato

## 1. Objetivo e contexto

Concretizar a segunda etapa da Fase 3 sobre o contrato `1.0.0` aceito na F3.1.
A tarefa prova que outcomes normais, parciais e falhas tipadas podem ser
representados por um conector totalmente sintético e que uma suíte comum
detecta violações de implementações futuras.

`F3_ROADMAP.md` é somente contexto. Esta tarefa não altera o ADR-0014 nem o
contrato público definido na F3.1.

## 2. Escopo autorizado

- conector simulado de registro empresarial em `intelligence.connectors.simulated`;
- configuração explícita e imutável de cenário;
- onze cenários determinísticos de resultado;
- busca de candidatos e detalhes com observações neutras;
- suíte tipada e reutilizável mantida exclusivamente em `tests/`;
- conectores deliberadamente incompatíveis somente nos testes;
- testes unitários e arquiteturais sem acesso externo;
- documentação e validação da F3.2.

## 3. Exclusões

Permanecem fora do escopo:

- F3.3, runner ou executor genérico;
- timeout, deadline ou cancelamento efetivos;
- retry, backoff, jitter, sleep e rate limiter;
- enforcement ou acumulação de budget;
- idempotência, fingerprint, cache e paginação entre chamadas;
- rede, HTTP, DNS, browser, filesystem, ambiente, subprocesso e fonte real;
- credenciais, banco, migrations e persistência de runs;
- jobs, filas, paralelismo, scheduler e orquestração;
- transições de investigação e resolução de entidades;
- criação de `Company`, evidência, claim, risco, decisão de crédito ou relatório;
- endpoint, autenticação ou frontend;
- dependências ou alterações em lockfiles.

Os cenários `TIMEOUT`, `RATE_LIMITED`, `CANCELLED` e `BUDGET_EXCEEDED` são
somente envelopes tipados produzidos pelo simulador. Eles não comprovam os
controles operacionais reservados à F3.3.

## 4. Desenho do simulador

`BusinessRegistryScenario` é um `StrEnum` fechado. O cenário é passado ao
construtor de `SimulatedBusinessRegistryConnector`; a query, o contexto e
estado externo nunca selecionam comportamento ocultamente.

O conector e seus envelopes são imutáveis. O descritor:

- usa IDs estáveis e explicitamente sintéticos;
- mantém o contrato `1.0.0`;
- declara cobertura `COUNTRY_SET` para `BR`;
- declara `COMPANY_IDENTITY` e `COMPANY_REGISTRY`;
- declara somente `SEARCH` e `FETCH_DETAILS`;
- suporta `TEST`;
- não declara `FETCH_DOCUMENT`.

`API` no campo `access_type` descreve apenas o formato lógico que o simulador
representa. Não comprova endpoint, acesso, licença ou disponibilidade. Do mesmo
modo, `BR` delimita somente a matriz de teste sintética e não afirma cobertura
de uma fonte real.

A assinatura uniforme `fetch_document` continua presente para satisfazer o
`Connector` Protocol e retorna `UNSUPPORTED_OPERATION`, com zero chamadas. A
seleção comum não a exerce porque a operação não está no descritor.

Todos os candidatos, identificadores, timestamps UTC, datas, custos, durações,
digests, mensagens e ordens são constantes. O código não usa relógio, UUID
aleatório, hashing, rede, arquivos, ambiente ou estado mutável de módulo.

As fixtures representam apenas organizações com nomes iniciados por
`Synthetic`, registros iniciados por `TEST-` e domínios reservados `.test`.
Nenhum dado de empresa, pessoa, documento ou fornecedor real é usado.

## 5. Catálogo de cenários

| Cenário | Busca e detalhes | Semântica comprovada |
|---|---|---|
| `SUCCESS` | `SUCCEEDED` | candidato tipado e seis observações neutras |
| `NO_RESULTS` | `NO_RESULTS` | resultado válido, vazio e sem erro |
| `MULTIPLE_CANDIDATES` | `SUCCEEDED` | dois candidatos distintos em ordem Alpha/Beta estável |
| `PARTIAL` | `PARTIAL` | conteúdo utilizável e warning `PARTIAL_DATA` |
| `RATE_LIMITED` | `FAILED` | `RATE_LIMITED` e `retry_after` fixo, sem retry |
| `TIMEOUT` | `FAILED` | `TIMEOUT` sem relógio ou espera |
| `UNAVAILABLE` | `FAILED` | `UNAVAILABLE` público e tipado |
| `INVALID_RESPONSE` | `FAILED` | tradução para `INVALID_RESPONSE`, sem payload bruto |
| `CANCELLED` | `CANCELLED` | sem item, artefato ou paginação tardia |
| `POLICY_BLOCKED` | `FAILED` | `POLICY_BLOCKED` sem decisão externa |
| `BUDGET_EXCEEDED` | `FAILED` | `BUDGET_EXCEEDED` sem cálculo de budget |

`fetch_details` de sucesso contém nome registrado, identificador empresarial,
situação registral, data de constituição, localidade e atividade econômica
sintética. Cada item usa `ObservationTypeCode` versionado e referencia o
candidato fornecido; nenhum item é entidade, evidência ou claim.

## 6. Suíte reutilizável

`ConnectorContractCase` recebe:

- factory sem argumentos para o conector;
- descritor esperado;
- query e contexto sintéticos válidos;
- candidato para detalhes;
- operações e status/código esperados;
- referência documental opcional para futuros conectores que declarem a operação.

`validate_connector_contract` é assíncrono e não conhece cenário, classe ou
atributo interno do simulador. A suíte permanece fora de produção e verifica:

1. conformidade estrutural com `Connector`;
2. descritor válido, estável, imutável, testável e em major suportada;
3. declaração prévia de toda operação exercitada;
4. igualdade na mesma instância e em nova instância equivalente;
5. tuplas e dataclasses imutáveis nos envelopes;
6. tipos de item específicos de cada operação;
7. `connector_id` dos candidatos e `source_id` dos snapshots;
8. vínculo de observações ao candidato fornecido;
9. semântica de `NO_RESULTS`, `PARTIAL` e `CANCELLED`;
10. códigos e representações públicas sem marcadores sensíveis;
11. estabilidade do descritor depois das operações.

Um driver de teste imediato exercita somente as corrotinas F3.2 que não
suspendem, sem criar event loop no Windows. A função assíncrona da suíte pode
ser aguardada normalmente por infraestrutura futura quando conectores reais
forem autorizados.

## 7. Prova negativa

Doubles incompatíveis existem apenas em
`tests/connectors/test_connector_contract_suite.py`. Eles usam `cast` onde a
informação genérica é apagada em runtime e demonstram a rejeição de:

- tipo incorreto em `search`;
- tipo incorreto em `fetch_details`;
- candidato com `connector_id` divergente;
- snapshot com `source_id` divergente;
- resultado não determinístico;
- descritor mutante;
- operação exercitada mas não declarada.

## 8. Estrutura de arquivos

```text
src/intelligence/connectors/simulated/
├── __init__.py
├── business_registry.py
└── scenarios.py

tests/connectors/
├── contract_suite.py
├── synthetic_fixtures.py
├── test_connector_contract_suite.py
└── test_simulated_business_registry.py
```

O teste arquitetural existente é ampliado; contratos F3.1, migrations,
lockfiles, API e frontend não são alterados.

## 9. Critérios de aceitação

- os onze cenários são exercitados sem I/O, relógio ou aleatoriedade;
- busca e detalhes retornam somente seus tipos de item;
- resultados iguais permanecem estruturalmente iguais;
- a suíte comum aceita o simulador e rejeita as sete violações;
- arquitetura bloqueia F3.3, fases posteriores e superfícies externas;
- branch coverage de `intelligence.connectors` permanece em pelo menos 90%;
- lint, formato, mypy estrito, testes, build, integração, Alembic e scanner passam;
- nenhuma dependência, migration, endpoint ou alteração web é introduzida;
- documentação registra resultados reais e F3.3 permanece bloqueada.

## 10. Validação

```text
uv sync --frozen --all-groups
pnpm install --frozen-lockfile
pnpm lint
pnpm format:check
pnpm typecheck
pnpm test
pnpm build
pnpm quality
pnpm test:integration
pnpm secrets
uv run pytest tests/connectors tests/architecture \
  --cov=intelligence.connectors --cov-branch \
  --cov-report=term-missing --cov-fail-under=90
uv run alembic current
uv run alembic check
```

No Windows, o comando focado deve preservar `--disable-socket` e pode substituir
os `addopts` globais apenas para isolar o relatório de cobertura da camada.

## 11. Riscos e limitações

- `ConnectorDescriptor` 1.0 não possui um modo “somente teste”; por isso o
  simulador não é registrado por composição de produção e só é instanciado
  explicitamente nos testes;
- igualdade estrutural detecta valores instáveis, mas ausência de mecanismos
  proibidos também depende da guarda AST;
- o simulador não prova qualidade, licença, disponibilidade ou acesso de fonte;
- outcomes de falha não provam retry, timeout, cancelamento, budget ou
  idempotência operacional.

## 12. Fronteira com a F3.3

F3.3 permanece não autorizada. Somente uma tarefa explícita futura poderá criar
runner, relógio monotônico, deadline efetivo, cancelamento cooperativo, retry,
backoff/jitter, budget enforcement, idempotência ou paginação operacional.
