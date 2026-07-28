Continue o projeto “Fator X Global Intelligence” a partir da F2.4.2 aprovada.

Execute exclusivamente:

# F3.1 — Contratos tipados e registro de conectores

Esta tarefa implementa a fundação puramente tipada dos conectores.

Não implemente conectores simulados ainda, não realize I/O e não crie controles
de retry, deadline efetivo ou idempotência. Esses componentes pertencem às
F3.2 e F3.3.

# INSTRUÇÃO DE PRECEDÊNCIA

Em caso de conflito:

1. a solicitação atual e este documento definem o escopo específico;
2. `AGENTS.md` define as regras gerais;
3. ADRs aceitos mantêm precedência arquitetural;
4. `docs/connector-contract.md` define a semântica funcional;
5. `F3_ROADMAP.md` serve apenas como contexto;
6. nenhuma fase futura pode ser antecipada.

# 1. Leitura obrigatória

Antes de alterar qualquer arquivo:

1. leia integralmente `AGENTS.md`;
2. leia `PLANS.md`;
3. leia `docs/architecture.md`;
4. leia `docs/connector-contract.md`;
5. leia `docs/source-policy.md`;
6. leia `docs/evidence-contract.md`;
7. leia `docs/testing-strategy.md`;
8. leia `docs/security.md`;
9. leia `docs/data-model.md`;
10. leia `docs/country-packs.md`;
11. leia `docs/dependencies.md`;
12. leia todos os ADRs aceitos;
13. revise os tipos fortes atuais do domínio;
14. revise as regras arquiteturais e scanner de segredos;
15. revise a configuração de mypy, Ruff e pytest;
16. inspecione o estado do Git;
17. apresente um plano resumido;
18. liste os arquivos que pretende criar ou modificar;
19. registre as decisões obrigatórias da seção 3.

Não altere código antes de concluir essa inspeção.

# 2. Limite da tarefa

## Incluído

- tipos fortes específicos da integração;
- versionamento semântico;
- vocabulários fechados;
- descritor imutável;
- cobertura explícita;
- contexto de chamada;
- query empresarial;
- candidato opaco;
- observações neutras;
- artefatos e referências;
- outcome genérico;
- protocolo assíncrono;
- registro de conectores;
- validação de compatibilidade;
- testes;
- ADR e documentação.

## Fora do escopo

- conectores simulados;
- conectores reais;
- HTTP ou outro cliente de rede;
- DNS;
- SSRF runtime;
- Playwright;
- scraping;
- browser;
- credenciais reais;
- retry;
- backoff;
- jitter;
- timeout efetivo;
- `asyncio.wait_for`;
- sleeper;
- idempotency store;
- cache;
- circuit breaker;
- rate limiter;
- execução paralela;
- jobs;
- workers;
- filas;
- persistência de connector runs;
- migrations;
- mudanças na Investigation;
- transições;
- orquestração;
- resolução de entidades;
- evidência canônica;
- claims;
- scoring;
- relatórios;
- endpoints;
- frontend;
- autenticação.

# 3. Decisões obrigatórias antes da implementação

Registre as decisões em ADR ou documento arquitetural antes de criar os tipos.

## 3.1 Localização e direção de dependências

A recomendação é criar:

`src/intelligence/connectors/`

Essa camada pode importar tipos estáveis do domínio, mas:

- domínio não importa connectors;
- application não deve depender de implementação concreta;
- connectors não importa persistência PostgreSQL;
- connectors não importa serviços de aplicação;
- connectors não importa evidências, claims, risk ou reporting.

Registre a direção escolhida.

## 3.2 Versionamento do contrato

Defina:

- versão inicial do contrato;
- política de compatibilidade por major;
- forma canônica de SemVer;
- rejeição de prerelease/build metadata caso não sejam necessários agora;
- comparação e hashing.

Não adicione biblioteca de SemVer sem necessidade comprovada.

## 3.3 Cobertura global

Conjunto vazio não significa global.

Escolha uma representação explícita, preferencialmente:

- `GLOBAL`; ou
- `COUNTRY_SET` com conjunto não vazio.

Garanta que estados contraditórios sejam rejeitados.

Atualize `docs/connector-contract.md` caso o contrato documental precise de um
campo explícito para cobertura global.

## 3.4 Vocabulário de capacidades

Defina enum fechado inicial, no mínimo:

- `COMPANY_IDENTITY`
- `COMPANY_REGISTRY`
- `OWNERSHIP`
- `CONTACTS`
- `FINANCIALS`
- `INSOLVENCY`
- `LEGAL_CASES`
- `SANCTIONS`
- `ADVERSE_MEDIA`
- `DOCUMENTS`

Esses nomes representam capacidades de coleta, não claims, risco ou cobertura
comercial prometida.

## 3.5 Representação de credenciais

Nesta fase não existe segredo.

O contexto pode conter somente:

- referência de configuração não secreta; ou
- handle opaco não serializável definido por Protocol.

Nunca permita token, senha, cookie ou API key nos dataclasses centrais.

`repr`, erros e testes não podem expor credenciais.

## 3.6 Deadline e cancelamento

F3.1 define apenas o contrato.

Escolha tipos que permitam F3.3 implementar deadline monotônico e cancelamento
cooperativo sem mudar a assinatura pública.

Não implemente espera, timeout ou cancelamento efetivo nesta tarefa.

## 3.7 Artefatos

Defina representação segura para:

- payload inline pequeno usado em testes futuros;
- referência opaca temporária.

Não use URL livre como credencial ou canal de acesso.

O tipo deve preservar:

- media type;
- tamanho;
- SHA-256;
- nome lógico opcional;
- modo de retenção/política;
- referência de origem.

Conteúdo externo é dado não confiável.

## 3.8 Observações

Observação não é fato.

Evite `dict[str, Any]`.

Defina um conjunto restrito de valores escalares, por exemplo:

- string;
- inteiro;
- booleano;
- `Decimal`;
- `date`;
- `datetime`.

Inclua representação original e normalizada opcional, moeda/unidade/período
quando aplicáveis, sem tentar modelar todos os futuros dados nesta fase.

# 4. Estrutura recomendada

A estrutura pode ser ajustada com justificativa:

```text
src/intelligence/connectors/
├── __init__.py
├── errors.py
├── identifiers.py
├── versions.py
├── enums.py
├── descriptor.py
├── context.py
├── queries.py
├── observations.py
├── artifacts.py
├── outcomes.py
├── protocol.py
└── registry.py
```

Testes sugeridos:

```text
tests/connectors/
├── test_identifiers.py
├── test_versions.py
├── test_descriptor.py
├── test_context.py
├── test_queries.py
├── test_observations.py
├── test_artifacts.py
├── test_outcomes.py
├── test_protocol.py
└── test_registry.py
```

Não crie `simulated/`, `execution/` ou `http/` nesta tarefa.

# 5. Identificadores de integração

Implemente tipos fortes e imutáveis para, no mínimo:

- `ConnectorId`;
- `SourceId`;
- `OperationId`;
- `RequestId`;
- `CandidateRefId`;
- `ArtifactRefId`.

Requisitos:

- impedir troca acidental entre tipos;
- validação de valor vazio e espaços;
- representação segura;
- igualdade e hashing previsíveis;
- IDs de execução podem usar UUID;
- IDs de conector/fonte devem ser estáveis e legíveis;
- candidato é opaco e escopado ao conector;
- não usar strings soltas no contrato.

Não mova esses IDs para o domínio sem justificativa. Eles pertencem à integração.

# 6. `SemanticVersion`

Implemente versão semântica mínima e imutável.

Requisitos:

- `major`, `minor`, `patch` inteiros não negativos;
- parse de `MAJOR.MINOR.PATCH`;
- rejeição de espaços, partes ausentes, sinais e componentes não numéricos;
- string canônica;
- ordenação;
- hashing;
- função explícita de compatibilidade por major.

Não implemente prerelease/build metadata sem necessidade.

# 7. Enums fechados

Implemente, no mínimo:

## Operações

- `SEARCH`
- `FETCH_DETAILS`
- `FETCH_DOCUMENT`

## Tipo de acesso

- `API`
- `FILE`
- `WEB_PUBLIC`
- `USER_UPLOAD`

## Modo

- `TEST`
- `PRODUCTION`

## Status

- `SUCCEEDED`
- `NO_RESULTS`
- `PARTIAL`
- `FAILED`
- `CANCELLED`

## Erros

- `INVALID_REQUEST`
- `UNSUPPORTED_COUNTRY`
- `UNSUPPORTED_CAPABILITY`
- `UNSUPPORTED_OPERATION`
- `AUTH_REQUIRED`
- `POLICY_BLOCKED`
- `RATE_LIMITED`
- `TIMEOUT`
- `UNAVAILABLE`
- `INVALID_RESPONSE`
- `BUDGET_EXCEEDED`
- `CANCELLED`
- `INTERNAL_ERROR`

## Retenção de artefato

- `STORE_ORIGINAL`
- `STORE_EXCERPT_ONLY`
- `REFERENCE_ONLY`
- `EPHEMERAL_PROCESSING`

Warnings devem utilizar código fechado e mensagem pública segura. Não crie
warning com payload arbitrário.

# 8. `ConnectorDescriptor`

Campos mínimos:

- `connector_id`;
- `version`;
- `contract_version`;
- `source_id`;
- cobertura explícita;
- países;
- capacidades;
- operações;
- tipo de acesso;
- `credential_ref_name` opcional;
- `supports_test_mode`;
- `max_page_size` opcional.

Invariantes:

- imutável;
- coleções convertidas para `frozenset`;
- ID não vazio;
- versões válidas;
- capacidades e operações não vazias;
- cobertura global não pode coexistir com lista arbitrária contraditória;
- cobertura por países exige conjunto não vazio;
- países são `CountryCode`;
- `max_page_size > 0` quando presente;
- `FETCH_DOCUMENT` não implica capacidade inexistente;
- `credential_ref_name` é somente nome de referência e nunca segredo;
- `supports_test_mode=False` não permite registro em registry de teste quando
  esse filtro for solicitado.

# 9. `ConnectorContext`

Campos mínimos:

- `workspace_id: WorkspaceId`;
- `investigation_id: InvestigationId`;
- `operation_id: OperationId`;
- `attempt`;
- `correlation_id: CorrelationId`;
- `request_id: RequestId`;
- contrato de deadline;
- orçamento restante opcional;
- idiomas/locales aceitos;
- versão da política da fonte;
- modo;
- referência/handle de credencial opcional;
- sinal de cancelamento.

Invariantes:

- `attempt >= 1`;
- budget usa `Money`, nunca float;
- locales são canônicos e não vazios;
- política possui versão não vazia;
- contexto é imutável;
- nenhum segredo aparece em `repr`;
- datetime, quando usado, possui fuso e UTC;
- sem funções anônimas não testáveis dentro de dataclass serializável.

Não implemente lógica de timeout.

# 10. `CompanyQuery`

Campos mínimos:

- país;
- nome original;
- nome normalizado;
- identificadores estruturados;
- domínio opcional;
- endereço estruturado opcional.

Crie tipos pequenos para:

- identificador empresarial consultado;
- endereço de busca;
- domínio.

Requisitos:

- país obrigatório;
- nome original e normalizado não vazios;
- string vazia não representa ausência;
- domínio não contém protocolo, caminho ou credenciais;
- identificador possui tipo e valor;
- não resolver entidade;
- não criar `Company`;
- não consultar pacote de país;
- imutável.

# 11. Candidato opaco

Implemente `CandidateRef` com:

- `candidate_ref_id`;
- `connector_id`;
- snapshot mínimo;
- país;
- nome apresentado;
- identificador principal opcional;
- domínio opcional.

Requisitos:

- nunca é `CompanyId`;
- nunca é tratado como entidade confirmada;
- escopado ao conector;
- não contém payload bruto;
- imutável;
- snapshot possui tamanho limitado.

# 12. Observações neutras

Implemente tipos para:

- `CandidateObservation`;
- `Observation`;
- `ObservationTypeCode`;
- valor original;
- valor normalizado opcional;
- unidade/moeda/período/idioma opcionais;
- locator de artefato ainda não canônico;
- timestamps opcionais;
- confiança de extração opcional;
- warnings de parsing.

Requisitos:

- não criar evidência;
- não criar claim;
- não afirmar correspondência;
- confiança de extração entre 0 e 1 usando `Decimal`, não float;
- timestamps com timezone;
- moeda usa `CurrencyCode`;
- nenhum `Any`;
- nenhuma mutação;
- ausência representada por `None`, não string vazia;
- locator não substitui o futuro contrato de evidência.

Mantenha o modelo mínimo. Não tente antecipar todos os predicados futuros.

# 13. Artefatos e referências

Implemente:

- `ArtifactPayload`;
- `ArtifactReference`.

## Payload

Requisitos:

- bytes imutáveis;
- media type obrigatório;
- tamanho calculado;
- SHA-256 calculado sobre os bytes;
- limite estrutural configurável somente no construtor, com default pequeno e
  seguro para fixtures;
- nome lógico opcional sanitizado;
- política de retenção explícita;
- conteúdo não aparece em `repr`.

## Referência

Requisitos:

- ID opaco;
- media type;
- tamanho conhecido opcional;
- digest opcional;
- expiração opcional;
- sem URL com credencial;
- sem método para buscar conteúdo nesta fase.

Não implemente storage ou stream.

# 14. Metadados de resultado

Implemente tipos imutáveis para:

## `SourceSnapshot`

- fonte;
- identificador lógico de origem;
- instante da consulta;
- publicação quando conhecida;
- sem token ou query secreta.

## `Pagination`

- quantidade retornada;
- `has_more`;
- cursor/continuation opaco opcional;
- cursor redigido no `repr`;
- invariantes coerentes.

## `ConnectorUsage`

- número de chamadas;
- bytes recebidos;
- duração;
- custo conhecido/estimado opcional;
- custo com `Money`;
- nenhum valor negativo;
- sem float monetário.

## `ConnectorWarning`

- código fechado;
- mensagem segura e limitada;
- sem payload.

## `ConnectorError`

- código fechado;
- mensagem segura;
- retry-after opcional;
- sem stack trace;
- sem corpo de resposta;
- sem token/cookie;
- erro não decide sozinho retry nesta fase.

# 15. `ConnectorOutcome[T]`

Implemente dataclass genérica imutável.

Campos mínimos:

- status;
- items;
- artifacts;
- source snapshot opcional conforme o tipo de falha;
- paginação opcional;
- uso;
- warnings;
- error opcional;
- response digest opcional.

Converta listas para tuples.

Invariantes obrigatórias:

## `SUCCEEDED`

- possui ao menos item ou artefato utilizável;
- não possui erro.

## `NO_RESULTS`

- não possui items;
- não possui artefatos utilizáveis;
- não possui erro;
- não é `FAILED`.

## `PARTIAL`

- possui ao menos item ou artefato utilizável;
- possui warning ou erro que explique a lacuna.

## `FAILED`

- possui erro;
- não possui item utilizável.

## `CANCELLED`

- erro, quando presente, utiliza código `CANCELLED`;
- não afirma sucesso;
- não possui item tardio publicável.

Outras regras:

- digest, quando presente, é SHA-256 canônico;
- status e error não podem se contradizer;
- paginação não aparece em falha sem resposta;
- tipos incompatíveis são rejeitados;
- factory methods nomeados podem ser usados para reduzir estados inválidos.

# 16. Protocol assíncrono

Crie `Connector[TSearch, TDetails]` ou Protocol equivalente, sem abstração
excessiva.

Operações lógicas:

- `describe() -> ConnectorDescriptor`
- `async search(query, context) -> ConnectorOutcome[CandidateObservation]`
- `async fetch_details(candidate_ref, context) -> ConnectorOutcome[Observation]`
- `async fetch_document(document_ref, context) -> ConnectorOutcome[ArtifactPayload]`
  somente quando declarado.

Requisitos:

- `runtime_checkable` apenas se houver benefício testado;
- sem implementação de rede;
- sem classe base obrigatória;
- sem acesso a repositório;
- sem commit;
- sem persistência;
- sem estado global;
- assinaturas coerentes com o descritor.

Defina como um conector que não oferece `FETCH_DOCUMENT` se comporta sem exigir
I/O. Preferencialmente a operação é rejeitada antes da chamada pelo registro ou
validador.

# 17. `ConnectorRegistry`

Crie registro explícito, instanciável e sem singleton global.

Operações mínimas:

- `register(connector)`;
- `get(connector_id)`;
- `list_all()`;
- `select(country, capability, operation, mode)`.

Requisitos:

- validar descriptor no registro;
- rejeitar ID duplicado;
- rejeitar major de contrato desconhecida;
- rejeitar Protocol incompatível quando detectável;
- seleção determinística;
- ordenação estável por `connector_id`;
- país/capacidade/operação não suportado nunca chama o conector;
- modo TEST respeita `supports_test_mode`;
- cobertura global explícita;
- não importar módulos dinamicamente;
- não ler entry points;
- não ler filesystem;
- não carregar configuração externa;
- não abrir rede;
- não persistir.

Pode existir um validador separado quando isso mantiver o registry pequeno.

# 18. Erros do contrato

Crie hierarquia mínima, por exemplo:

- `ConnectorContractError`;
- `InvalidConnectorDescriptorError`;
- `DuplicateConnectorError`;
- `UnsupportedContractVersionError`;
- `ConnectorNotFoundError`;
- `InvalidConnectorOutcomeError`.

Mensagens:

- seguras;
- sem `repr` de contexto completo;
- sem credenciais;
- sem payload;
- sem stack externa;
- úteis para testes.

Não misture falha retornada pelo fornecedor com erro de programação do contrato.

# 19. Testes unitários obrigatórios

## Identificadores

- válidos;
- vazios;
- espaços;
- tipos diferentes;
- hashing;
- repr seguro.

## SemVer

- parse;
- formato canônico;
- ordenação;
- compatibilidade;
- inválidos.

## Descriptor

- global;
- países;
- estados contraditórios;
- capability vazia;
- operation vazia;
- país inválido;
- page size;
- imutabilidade;
- credential ref segura.

## Context

- IDs fortes;
- attempt;
- budget Decimal;
- locales;
- UTC;
- credential não aparece no repr;
- cancelamento apenas como contrato.

## Query

- nome;
- país;
- domínio;
- identificadores;
- endereço;
- strings vazias.

## Candidate

- opacidade;
- escopo do conector;
- não confundir com CompanyId;
- snapshot limitado.

## Observation

- valores suportados;
- Decimal;
- confiança;
- período;
- timestamps;
- rejeição de Any/dict arbitrário.

## Artifact

- digest;
- tamanho;
- media type;
- limite;
- repr sem bytes;
- referência segura.

## Outcome

Teste cada status válido e todas as combinações contraditórias:

- success vazio;
- no results com item;
- partial sem lacuna;
- failed sem error;
- failed com item;
- cancelled com sucesso;
- digest inválido;
- paginação inválida;
- coleções imutáveis.

## Registry

- registro;
- duplicidade;
- contrato incompatível;
- get ausente;
- listagem estável;
- seleção por país;
- seleção global;
- capability;
- operation;
- modo test;
- nenhuma chamada durante seleção.

# 20. Testes arquiteturais

Atualize os testes AST para garantir:

- domínio não importa connectors;
- connectors não importa persistência PostgreSQL;
- connectors não importa repositories;
- connectors não importa application services;
- connectors não importa evidence;
- connectors não importa claims;
- connectors não importa risk;
- connectors não importa reporting;
- connectors não importa FastAPI/Pydantic;
- nenhum módulo abre socket;
- nenhum módulo cria engine;
- nenhum módulo faz I/O durante import;
- registry não usa importlib, entry points ou filesystem;
- nenhum conector real ou simulado foi criado;
- nenhuma migration foi adicionada;
- nenhuma dependência foi adicionada sem registro.

# 21. Segurança

Confirme:

- nenhuma rede;
- nenhum segredo;
- nenhum token;
- nenhum cookie;
- nenhum payload externo em log;
- bytes não aparecem em repr;
- cursor é redigido;
- referências não contêm credenciais;
- erros são limitados;
- nenhum conteúdo é executado;
- nenhum import dinâmico;
- nenhum fallback de cobertura global;
- scanner de segredos aprovado.

# 22. Dependências

Não são esperadas novas dependências.

Caso seja proposta alguma:

1. interrompa;
2. justifique por que biblioteca padrão não basta;
3. registre versão, licença, manutenção e riscos;
4. atualize lockfiles e `docs/dependencies.md`;
5. não adicione cliente HTTP nesta tarefa.

# 23. Documentação

Atualize:

- `AGENTS.md` para registrar F2.4.2 concluída e F3.1 como tarefa atual;
- `PLANS.md`;
- `docs/architecture.md`;
- `docs/connector-contract.md`;
- `docs/testing-strategy.md`;
- `docs/security.md`;
- `docs/dependencies.md` somente se necessário;
- `docs/README.md`;
- índice de ADRs.

Crie ADR sobre:

- localização da camada;
- versionamento;
- cobertura global explícita;
- neutralidade das observações;
- registro sem descoberta dinâmica.

Crie:

`docs/validation/f3.1-connector-contracts-registry.md`

Registre:

- decisões;
- arquivos;
- tipos;
- invariantes;
- versão do contrato;
- matriz de cobertura;
- registry;
- testes;
- cobertura;
- gates;
- limitações;
- escopo adiado para F3.2 e F3.3.

# 24. Gates obrigatórios

Execute:

- `uv sync --frozen --all-groups`
- `pnpm install --frozen-lockfile`
- `pnpm lint`
- `pnpm format:check`
- `pnpm typecheck`
- `pnpm test`
- `pnpm build`
- `pnpm quality`
- `pnpm test:integration`
- `alembic upgrade head`
- `alembic check`
- scanner de segredos.

Requisitos:

- nenhum teste acessa internet;
- nenhum teste crítico é skipped;
- cobertura total permanece acima do gate;
- camada connectors deve atingir pelo menos 90% de branch coverage;
- nenhuma migration nova;
- nenhum diff de metadata;
- nenhum arquivo gerado no commit.

# 25. Critérios de conclusão

F3.1 somente estará concluída quando:

1. tipos de integração forem fortes e imutáveis;
2. versão do contrato for explícita;
3. cobertura global não depender de conjunto vazio;
4. descriptor inválido for rejeitado;
5. credencial não puder vazar pelos envelopes;
6. query não criar entidade canônica;
7. candidato não puder ser confundido com Company;
8. observação não puder ser tratada como claim;
9. artefato possuir digest e política;
10. outcomes contraditórios forem impossíveis;
11. Protocol for assíncrono e sem implementação externa;
12. registry for determinístico e sem descoberta dinâmica;
13. seleção não executar I/O;
14. testes arquiteturais preservarem as fronteiras;
15. nenhum simulador, executor ou conector real existir;
16. nenhum HTTP/dependência nova existir;
17. todos os gates passarem;
18. documentação estiver consistente.

# 26. Git e pacote final

Depois dos gates:

- `git status`;
- `git diff --check`;
- `git diff --stat`.

Confirme ausência de:

- `.env`;
- caches;
- builds;
- dependências instaladas;
- bancos;
- volumes;
- credenciais;
- fixtures de fonte real;
- respostas externas;
- migration nova.

Crie o commit:

`feat: define connector contracts and registry`

Não execute push.

Gere:

`git archive --format=zip --output=FatorX_Global_Intelligence_F3_1.zip HEAD`

Apresente:

- hash curto e completo do commit;
- SHA-256 do ZIP;
- tamanho;
- quantidade de arquivos;
- versão do contrato;
- ADR criado;
- tipos e enums;
- registry;
- testes;
- branch coverage da camada;
- gates;
- limitações;
- itens explicitamente adiados para F3.2/F3.3;
- não avance para F3.2.
