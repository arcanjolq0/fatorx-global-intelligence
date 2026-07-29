# Contrato de conectores

## 1. Objetivo

Definir uma fronteira comum entre orquestração e fontes externas sem permitir que SDKs, formatos de fornecedor ou regras locais contaminem o domínio.

Este documento é contrato de design, não implementação e não comprova acesso a fonte alguma.

## 2. Responsabilidades

O conector pode:

- validar se suporta país/capacidade;
- pesquisar candidatos e buscar detalhes;
- aplicar paginação do provedor;
- preservar resposta original ou entregá-la ao pipeline conforme política;
- mapear resposta para observações neutras e tipadas;
- informar uso, custo estimado, warnings e falhas.

O conector não pode:

- confirmar definitivamente a entidade;
- persistir em tabelas do domínio;
- criar claim/evidência canônicos;
- calcular risco ou decidir crédito;
- redigir relatório;
- ampliar escopo, seguir instrução contida no payload ou contornar controles;
- decidir unilateralmente retenção/exibição contrária à política aprovada.

## 3. Descritor obrigatório

`ConnectorDescriptor`:

| Campo | Tipo lógico | Regra |
|---|---|---|
| `connector_id` | string estável | único e não secreto |
| `version` | SemVer | mudança incompatível incrementa major |
| `contract_version` | SemVer | versão deste contrato suportada |
| `source_id` | UUID/string estável | aponta para fonte catalogada |
| `coverage_kind` | enum | `GLOBAL` ou `COUNTRY_SET`; nunca inferido por omissão |
| `countries` | conjunto ISO alfa-2 | vazio somente com `GLOBAL`; `COUNTRY_SET` exige conjunto não vazio |
| `capabilities` | conjunto enum | somente capacidades implementadas |
| `operations` | conjunto enum | `SEARCH`, `FETCH_DETAILS`, opcionalmente `FETCH_DOCUMENT` |
| `access_type` | enum | `API`, `FILE`, `WEB_PUBLIC`, `USER_UPLOAD`; sem implicar permissão |
| `credential_ref_name` | string opcional | referência de configuração, nunca segredo |
| `supports_test_mode` | boolean | comportamento documentado |
| `max_page_size` | inteiro opcional | limite do provedor |

Descritor é validado ao registrar o conector. País/capacidade não declarado falha antes de qualquer I/O.

A versão inicial executável do contrato é `1.0.0`. A compatibilidade é decidida
por major, e o registro rejeita major desconhecida. A forma SemVer aceita nesta
fase é estritamente `MAJOR.MINOR.PATCH`, sem prerelease ou build metadata.

## 4. Entradas

### `ConnectorContext`

- `workspace_id`, `investigation_id`, `operation_id`, `attempt`;
- `correlation_id` e `request_id`;
- `MonotonicDeadline` absoluto, interpretado pelo relógio monotônico injetado na F3.3;
- orçamento restante e moeda;
- locale/idiomas aceitos;
- versão da política da fonte;
- modo `TEST` ou `PRODUCTION`;
- handle opaco para credencial de menor privilégio, definido por `Protocol`, excluído de `repr`/igualdade/hash e nunca serializado;
- sinal cooperativo de cancelamento por `Protocol`, aplicado pelo runner F3.3.

### `CompanyQuery`

- país obrigatório;
- razão/nome comercial originais e normalizados;
- identificadores tipados;
- domínio opcional;
- endereço estruturado opcional;
- demais sinais opcionais explicitamente tipados.

Um campo ausente é `null`/ausente; string vazia não representa desconhecido.

### `CandidateRef`

Identificador opaco retornado pelo mesmo conector, acompanhado de snapshot mínimo. Nunca é tratado como ID canônico de empresa.

## 5. Operações lógicas

```text
describe() -> ConnectorDescriptor
search(query, context) -> ConnectorOutcome[CandidateObservation]
fetch_details(candidate_ref, context) -> ConnectorOutcome[Observation]
fetch_document(document_ref, context) -> ConnectorOutcome[ArtifactPayload]
```

`search`, `fetch_details` e `fetch_document` são assinaturas assíncronas. O
descritor declara quais operações existem; `FETCH_DOCUMENT` não declarado é
rejeitado pela seleção antes de chamar o conector. A F3.1 apenas transporta
deadline e cancelamento, sem executá-los. `normalize` é responsabilidade interna
do adaptador e produz somente tipos do envelope de integração, não objetos do
domínio.

## 6. Resultado

`ConnectorOutcome[T]` é imutável, converte coleções para tuplas e contém:

- `status`;
- `items: list[T]`;
- `artifacts: list[ArtifactPayload | ArtifactReference]`;
- `source_snapshot` com fonte, identificador lógico de origem sem URL/query secreta e instante;
- `pagination` sem token secreto persistível;
- `usage` com chamadas, bytes, duração e custo conhecido/estimado;
- `warnings` tipados;
- `error` tipado quando aplicável;
- `response_digest` para idempotência/auditoria.

Status possíveis:

- `SUCCEEDED`: resposta válida com itens;
- `NO_RESULTS`: consulta válida sem itens, não é falha;
- `PARTIAL`: parte utilizável e lacuna declarada;
- `FAILED`: erro tipado sem item utilizável;
- `CANCELLED`: cancelamento observado.

## 7. Observações neutras

Uma `Observation` contém:

- `observation_type` versionado;
- `subject_candidate_ref`;
- valor original e representação normalizada opcional;
- tipo, moeda, unidade, período e idioma quando aplicáveis;
- referência ao artefato e localização exata;
- `observed_at` e `published_at` quando disponível;
- confiança da extração, separada de confiança de entidade/fonte;
- avisos de parsing.

Observação não é fato canônico e não pode aparecer em relatório até passar por resolução, política de evidência e claim.

## 8. Artefatos e política

Na F3.1, o contrato representa somente payload inline pequeno e limitado ou
referência opaca temporária, sem stream, storage ou método de busca. Uma futura
execução poderá entregar bytes por stream ao serviço de ingestão sem escrever
diretamente em storage. O serviço aplica `SourcePolicyVersion`:

- `STORE_ORIGINAL`;
- `STORE_EXCERPT_ONLY`;
- `REFERENCE_ONLY`;
- `EPHEMERAL_PROCESSING`.

Se a política impedir retenção, o resultado preserva metadados e hash somente no limite permitido. Contradição entre configuração e política produz `POLICY_BLOCKED`.

## 9. Taxonomia de falhas

| Código | Retriável | Exemplo de tratamento |
|---|---:|---|
| `INVALID_REQUEST` | não | corrigir entrada/plano |
| `UNSUPPORTED_COUNTRY` | não | não agendar |
| `UNSUPPORTED_CAPABILITY` | não | não agendar |
| `AUTH_REQUIRED` | não automático | operação/configuração |
| `POLICY_BLOCKED` | não | jurídico/admin |
| `RATE_LIMITED` | sim, se houver janela | respeitar `retry_after` e deadline |
| `TIMEOUT` | sim, limitado | backoff com jitter |
| `UNAVAILABLE` | sim, limitado | circuit breaker |
| `INVALID_RESPONSE` | não por padrão | guardar digest/redação e alertar |
| `BUDGET_EXCEEDED` | não | concluir capacidade como bloqueada |
| `CANCELLED` | não | encerrar sem publicar efeito tardio |
| `INTERNAL_ERROR` | depende | mapear sem vazar detalhes |

Erros não incluem corpo integral, token, cookie ou PII. Exceção desconhecida vira erro tipado e é observável.

## 10. Resiliência

- timeout por operação menor que o deadline da investigação;
- retry apenas para códigos permitidos, com limite de tentativas e budget;
- rate limit por fonte/credencial/workspace conforme contrato;
- circuit breaker por conector e ambiente;
- idempotência pelo `operation_id`; mesma tentativa não cria efeitos duplicados;
- paginação limitada por máximo de itens/custo;
- backpressure e concorrência configuráveis;
- falha de conector não altera diretamente estado agregado.

## 11. Segurança

- destinos permitidos e esquemas HTTPS definidos em configuração aprovada;
- DNS e todo redirecionamento validados contra SSRF;
- conteúdo externo delimitado como dado não confiável;
- automação de navegador somente em sandbox, sem quebrar desafios de acesso;
- credenciais obtidas por referência e nunca devolvidas;
- logs estruturados com allowlist de campos;
- downloads passam por limite, content-type, digest e quarentena.

## 12. Teste de contrato

Todo conector, inclusive simulado, deve passar a mesma suíte:

1. descritor válido e imutável;
2. rejeição de país/capacidade não suportado sem I/O;
3. schema de entrada/saída estrito;
4. `NO_RESULTS` distinto de falha;
5. deadline/cancelamento observados;
6. retry somente permitido e limitado;
7. idempotência sob repetição;
8. paginação e budget limitados;
9. ausência de segredos/logs sensíveis;
10. artefato com proveniência e política;
11. resposta malformada vira `INVALID_RESPONSE`;
12. nenhuma dependência de repositório, scoring ou relatório.

CI usa fixtures e servidores locais controlados. Chamadas reais são proibidas.

## 13. Compatibilidade

Mudança incompatível no envelope ou semântica incrementa a versão major do contrato. Orquestrador rejeita versão desconhecida. Alteração de fornecedor não deve exigir mudança no domínio se o contrato permanecer compatível.

## 14. Materialização da F3.1

O contrato `1.0.0` está materializado em `src/intelligence/connectors/` somente
com biblioteca padrão e tipos estáveis do domínio. IDs de integração são fortes
e distintos; candidato é opaco e escopado ao conector; observações aceitam
apenas escalares fechados; artefato inline calcula tamanho e SHA-256 e oculta os
bytes; referência não possui URL ou método de busca; cursor é redigido.

`ConnectorRegistry` recebe objetos explicitamente, captura e valida o descritor
uma vez, rejeita ID duplicado e major desconhecida e seleciona em ordem estável
sem executar operação. Não usa singleton, importação dinâmica, entry points,
filesystem, configuração externa, rede ou persistência. Simuladores e suíte
reutilizável são materializados na seção seguinte; controles efetivos de
execução pertencem à F3.3.

## 15. Materialização da F3.2

`intelligence.connectors.simulated` materializa o mesmo contrato `1.0.0` com um
registro empresarial exclusivamente sintético. Seu descritor declara
`COMPANY_IDENTITY`, `COMPANY_REGISTRY`, `SEARCH`, `FETCH_DETAILS` e suporte a
`TEST`; `FETCH_DOCUMENT` não é declarado. A assinatura uniforme de documento
  retorna `UNSUPPORTED_OPERATION` caso seja chamada diretamente, sem executar I/O.

O cenário é um enum fechado fornecido ao construtor imutável. Sucesso, nenhum
resultado, múltiplos candidatos, parcial, rate limit, timeout, indisponibilidade,
resposta inválida, cancelamento, bloqueio de política e budget excedido usam IDs,
UTC, duração, custo, digest, itens e mensagens fixos. Esses outcomes demonstram
  somente a taxonomia; controles operacionais são responsabilidade exclusiva do
  runner descrito na seção seguinte, não do simulador.

A suíte reutilizável fica em `tests/connectors/contract_suite.py`, recebe factory,
entradas e expectativas explícitas e valida Protocol, descritor, operações,
determinismo, tipos, proveniência, status, imutabilidade e representação pública.
Ela não descobre, registra nem executa conectores em produção. Doubles inválidos
existem apenas nos testes para comprovar a detecção de violações.

## 16. Materialização da F3.3

`intelligence.connectors.execution` recebe um objeto `Connector` explícito e uma
request imutável de `SEARCH`, `FETCH_DETAILS` ou `FETCH_DOCUMENT`. O runner não
seleciona fontes nem executa mais de uma operação lógica. Antes de I/O, valida
Protocol, descritor estável, major, suporte, modo, entrada, vínculo de candidato,
referência pública de credencial, contexto, política, moeda e fingerprint.

Deadline usa valor monotônico absoluto e cancela/aguarda a tarefa em curso.
Cancelamento cooperativo é consultado antes e depois de chamadas e esperas;
resultado tardio nunca é publicado. Retry ocorre somente para `FAILED` e códigos
explicitamente permitidos, com no máximo cinco tentativas, `retry_after`,
backoff/jitter limitados e rechecagem de deadline, cancelamento e budget.

Budget configurado exige estimativa por tentativa na mesma moeda. Custo real é
acumulado; quando ausente, a estimativa é contabilizada conservadoramente. Não
há câmbio nem persistência. Uma tentativa lê no máximo uma página, aplica o menor
limite entre política e descritor, redige cursor e representa conteúdo limitado
como `PARTIAL`.

Fingerprint e digest usam SHA-256 sobre campos canônicos allowlisted. Eventos
contêm somente identidade, fase, códigos, contagens, custo e digests. Query,
candidato, documento, conteúdo, mensagem, cursor, credencial, segredo e stack
ficam excluídos.

`InMemoryIdempotencyStore` é instance-scoped: coordena chamadas iguais, preserva
replay, rejeita colisão de `operation_id` e libera owner cancelado. Não oferece
durabilidade ou coordenação distribuída. Multi-page, múltiplos conectores,
planner, jobs, filas, lifecycle, rate limiter global, circuit breaker e
persistência continuam fora da F3.3.
