# F3.3 — Controles de execução de uma única operação de conector

Status: **IMPLEMENTADA — AGUARDANDO REVISÃO INDEPENDENTE**.

## 1. Objetivo, contexto e autorização

Esta tarefa materializa os controles operacionais do gate G3 sobre os contratos
`1.0.0` e o simulador aceitos nas F3.1/F3.2. A autorização explícita de
2026-07-29 limita a execução a uma única operação lógica (`SEARCH`,
`FETCH_DETAILS` ou `FETCH_DOCUMENT`) de um único objeto `Connector` fornecido
pelo chamador.

`F3_ROADMAP.md` continua sendo apenas contexto. Esta entrega não aceita o gate
G3, não conclui a Fase 3 por conta própria e não autoriza a Fase 4.

## 2. Escopo

- requests discriminadas e imutáveis por operação;
- runner assíncrono de operação única;
- preflight de contrato, suporte, entrada, credencial, contexto e budget;
- deadline monotônico efetivo e cancelamento cooperativo;
- retry limitado, backoff exponencial limitado e jitter injetável;
- accounting monetário entre tentativas, sem conversão de moeda;
- fingerprint canônico da requisição e digest estrutural do resultado;
- idempotência atômica por `operation_id` em memória;
- coordenação de chamadas idênticas concorrentes e rejeição de colisão;
- uma página por tentativa, com limites de itens e artefatos;
- validação runtime do outcome antes de publicação;
- eventos estruturais imutáveis, sem conteúdo externo;
- testes determinísticos e guardas arquiteturais.

## 3. Exclusões

Não há planner, seleção ou paralelismo de conectores, fan-out/fan-in, scheduler,
job, worker, fila, outbox, circuit breaker, rate limiter compartilhado, cache
geral, persistência, migration, banco, HTTP, DNS, socket, browser, filesystem,
ambiente, subprocesso, conector real, endpoint, frontend ou autenticação.

O runner não altera `Investigation`, não cria `Company`, evidência, claim,
contradição, score, decisão de crédito ou relatório. Também não resolve
identidades, não agrega fontes e não segue páginas.

## 4. Desenho do runner e contratos públicos

`ConnectorOperationRunner` recebe no construtor quatro portas pequenas:
`MonotonicClock`, `ExecutionSleeper`, `JitterSource` e `IdempotencyStore`. Não há
estado ou composição global. `execute()` possui overloads para:

- `SearchConnectorOperation` → candidatos;
- `FetchDetailsConnectorOperation` → observações;
- `FetchDocumentConnectorOperation` → payload de artefato.

Cada request carrega explicitamente conector, capacidade, país, entrada própria,
`ConnectorContext` e `ConnectorExecutionPolicy`. Não existe payload genérico,
`Any`, `dict` livre ou `**kwargs` na fronteira.

`ConnectorExecutionResult[T]` preserva o `ConnectorOutcome[T]` da fonte e
acrescenta tentativas iniciadas, uso total, fingerprint, digest, status de
idempotência, metadados estruturais, eventos e código de controle opcional. Os
requests, políticas, resultados e eventos são dataclasses congeladas.

## 5. Preflight antes de I/O

Antes de reservar idempotência ou iniciar tentativa, o runner valida:

1. conformidade runtime com `Connector`;
2. descritor válido, estável e em major suportada;
3. país, capacidade, operação e modo declarados;
4. tipo e coerência da entrada discriminada;
5. vínculo do candidato ao conector e país em detalhes;
6. referência pública de credencial exatamente quando declarada;
7. invariantes do contexto e tentativa base igual a 1;
8. coerência e limites da política;
9. moeda e estimativa exigida quando há budget;
10. construção segura do fingerprint.

Falhas usam `ConnectorExecutionPreflightError` e mensagens públicas redigidas.
Não chamam conector, não dormem e não reservam custo.

## 6. Deadline e cancelamento

O prazo é o valor absoluto de `MonotonicDeadline`, comparado somente por
`MonotonicClock`. Durante uma chamada, a tarefa do conector disputa com
`ExecutionSleeper.sleep_until()`. Ao vencer o deadline, o runner cancela e
aguarda a tarefa antes de publicar `TIMEOUT`; outcome tardio é descartado.

O mesmo sinal cooperativo é entregue em todas as tentativas. Cancelamento é
verificado antes da reserva, antes de cada tentativa e backoff e imediatamente
depois da chamada. Conteúdo devolvido após cancelamento não é publicado, não é
armazenado para replay e não provoca retry.

## 7. Retry, backoff e jitter

`ConnectorExecutionPolicy` limita `max_attempts` entre 1 e 5. Por padrão,
somente `RATE_LIMITED`, `TIMEOUT` e `UNAVAILABLE` são retriáveis.
`INVALID_RESPONSE` e `INTERNAL_ERROR` exigem inclusão explícita; códigos de
preflight, política, autenticação, budget e cancelamento nunca são aceitos na
lista.

Retry ocorre apenas para `FAILED`. Backoff é exponencial a partir de
`base_backoff`, limitado por `max_backoff`; `retry_after` é o piso quando
presente. O jitter aditivo vem de `JitterSource`, deve ser não negativo e não
exceder `max_jitter`. O adapter padrão usa jitter zero. Deadline, cancelamento e
budget são reavaliados antes de qualquer espera e tentativa seguinte.

## 8. Budget e accounting

Budget ausente significa somente ausência de enforcement monetário nesta
chamada. Quando `budget_remaining` está presente, a política deve declarar
`estimated_attempt_cost` na mesma moeda. A estimativa é verificada antes de cada
tentativa.

Após a chamada, o custo real de `ConnectorUsage` substitui a estimativa para
accounting; se ausente, a estimativa é usada conservadoramente. Uso de todas as
tentativas é acumulado. Moeda divergente produz `INVALID_RESPONSE`, sem câmbio.
Um custo real acima do saldo é contabilizado sem expor saldo negativo e o
resultado final é `BUDGET_EXCEEDED`.

## 9. Fingerprint, idempotência e concorrência

O fingerprint SHA-256 usa codificação canônica explícita da semântica pública:
workspace, investigação, conector e versões, operação, capacidade, país, modo,
versão da política da fonte, entrada tipada e referência pública de credencial.
Também inclui os controles versionados da política que mudam a execução.

Ficam excluídos deadline, attempt, budget restante, timestamps, estado de
cancelamento, objeto/segredo de credencial, payload bruto, cursores, `repr` e
serialização genérica.

`InMemoryIdempotencyStore` é instance-scoped e coordena atomicamente por
`operation_id`:

- o primeiro chamador reserva e executa;
- replay concluído devolve o resultado lógico armazenado, marcado `REPLAYED`;
- concorrente idêntico espera a mesma conclusão sob seu próprio deadline, sem
  segunda chamada ou custo;
- fingerprint diferente gera conflito tipado e não chama o conector;
- cancelamento excepcional do owner libera a reserva para nova tentativa.

Não há persistência nem singleton.

## 10. Limites e paginação

Cada tentativa faz exatamente uma chamada. O limite de itens é o menor entre
política e `descriptor.max_page_size`; artefatos possuem limite próprio. Excesso
gera `PARTIAL` e warning `TRUNCATED`. `has_more=True` gera
`PAGINATION_LIMITED`, remove o cursor publicável e nunca dispara nova página.
Contagem contraditória produz `INVALID_RESPONSE`. Paginação multi-page pertence
a uma fase futura de integração/orquestração.

## 11. Validação runtime, digest e observabilidade

Antes de publicar, o runner valida o tipo do outcome e dos itens, `source_id`,
vínculo de candidato/observação, paginação, status sem conteúdo indevido,
mensagens públicas, moeda e formato de digest. Resposta incompatível vira
`INVALID_RESPONSE`; exceção crua vira `INTERNAL_ERROR`. Texto e objeto externos
não são propagados.

O digest SHA-256 contém somente fingerprint, IDs e versões, operação, status e
código finais, tentativas, uso agregado, digest de resposta/artefato, contagens
e códigos de warning. Não inclui query, identificador empresarial, endereço,
mensagem, cursor, conteúdo, credencial ou stack.

Eventos imutáveis usam allowlist de identidade, tentativa, fase, status, códigos,
delay, custo, fingerprint e digest. Não há configuração global de logging.

## 12. Estrutura de arquivos

```text
src/intelligence/connectors/execution/
├── __init__.py
├── contracts.py
├── errors.py
├── fingerprint.py
├── idempotency.py
├── policies.py
├── ports.py
├── runner.py
└── validation.py

tests/connectors/execution/
├── doubles.py
├── test_budget_idempotency.py
├── test_contract_port_edges.py
├── test_deadline_cancellation.py
├── test_limits_runtime_validation.py
├── test_policy_preflight.py
├── test_retry.py
└── test_success_fingerprint.py
```

O teste arquitetural existente foi ampliado. Simulador F3.2, contratos F3.1,
migrations, lockfiles, API e web não foram alterados.

## 13. Critérios de aceitação

- as três operações usam requests e resultados tipados;
- todo preflight bloqueia I/O, sleep e custo;
- timeout encerra a tarefa e bloqueia resultado tardio;
- cancelamento impede publicação e retry;
- retry, backoff, `retry_after` e jitter obedecem limites explícitos;
- budget é verificado e contabilizado em moeda única;
- replay e concorrência não duplicam chamada ou custo;
- colisão é rejeitada antes da chamada;
- uma única página e limites de conteúdo são aplicados;
- outcome, fingerprint, digest e eventos são validados/redigidos;
- branch coverage da área crítica é pelo menos 90%;
- F3.1/F3.2 e os gates completos permanecem aprovados;
- nenhuma dependência, migration ou fase posterior é introduzida.

## 14. Comandos de validação

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
uv run pytest -o "addopts=--strict-config --strict-markers --disable-socket" \
  tests/connectors/execution tests/architecture \
  --cov=intelligence.connectors.execution --cov-branch \
  --cov-report=term-missing --cov-fail-under=90
uv run alembic current
uv run alembic check
```

Resultados reais ficam em
`docs/validation/f3.3-connector-execution-controls.md`.

## 15. Riscos, limitações e fronteira com a Fase 4

- O store em memória coordena apenas uma instância de processo e não sobrevive a
  reinício; idempotência distribuída exige decisão futura.
- Jitter de produção é zero nesta fase; a porta permite política futura sem
  aleatoriedade global.
- O custo estimado vem da política porque o descritor `1.0.0` não possui tabela
  de preço; não há cotação, câmbio ou reserva persistida.
- Cancelamento de Python impede publicação pelo runner, mas código externo deve
  cooperar para interromper sua própria atividade subjacente.
- Uma tentativa consome no máximo uma página e nenhum cursor é seguido.
- Eventos retornados preparam auditoria futura, mas não são persistidos nem
  enviados a logging/telemetria.

Fase 4 continua proibida. Somente autorização e revisão independentes futuras
podem aceitar G3 e iniciar planner, múltiplos conectores, jobs, lifecycle,
persistência ou resolução de entidades.
