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
| `countries` | conjunto ISO alfa-2 | vazio não significa global |
| `capabilities` | conjunto enum | somente capacidades implementadas |
| `operations` | conjunto enum | `SEARCH`, `FETCH_DETAILS`, opcionalmente `FETCH_DOCUMENT` |
| `access_type` | enum | `API`, `FILE`, `WEB_PUBLIC`, `USER_UPLOAD`; sem implicar permissão |
| `credential_ref_name` | string opcional | referência de configuração, nunca segredo |
| `supports_test_mode` | boolean | comportamento documentado |
| `max_page_size` | inteiro opcional | limite do provedor |

Descritor é validado ao registrar o conector. País/capacidade não declarado falha antes de qualquer I/O.

## 4. Entradas

### `ConnectorContext`

- `workspace_id`, `investigation_id`, `operation_id`, `attempt`;
- `correlation_id` e `request_id`;
- `deadline_at` monotonicamente aplicável;
- orçamento restante e moeda;
- locale/idiomas aceitos;
- versão da política da fonte;
- modo `TEST` ou `PRODUCTION`;
- handle para credencial de menor privilégio, resolvido pelo adaptador e nunca serializado;
- função de cancelamento.

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
fetch_document(document_ref, context) -> ConnectorOutcome[ArtifactPayload]  # opcional
```

Todas são assíncronas, canceláveis e respeitam deadline. `normalize` é responsabilidade interna do adaptador e produz somente tipos do envelope de integração, não objetos do domínio.

## 6. Resultado

`ConnectorOutcome[T]` contém:

- `status`;
- `items: list[T]`;
- `artifacts: list[ArtifactPayload | ArtifactReference]`;
- `source_snapshot` com fonte, URL/endpoint lógico e instante;
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

O conector entrega bytes por stream ou referência temporária ao serviço de ingestão. Não escreve diretamente em storage. O serviço aplica `SourcePolicyVersion`:

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
