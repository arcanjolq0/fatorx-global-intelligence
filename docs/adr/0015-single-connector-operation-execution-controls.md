# ADR-0015 — Controles locais de uma única operação de conector

- Status: Accepted
- Data: 2026-07-29

## Contexto

O ADR-0014 fixa o contrato `1.0.0`, o `Connector` assíncrono e o registro
explícito. A F3.2 prova o contrato com simuladores, mas seus outcomes de timeout,
cancelamento e budget são apenas dados. A F3.3 precisa aplicar controles reais
sem antecipar a orquestração persistida e multi-conector da Fase 4.

## Decisão

### Fronteira de execução

Os controles ficam em `intelligence.connectors.execution`. Um
`ConnectorOperationRunner` recebe explicitamente um conector e uma request
discriminada de `SEARCH`, `FETCH_DETAILS` ou `FETCH_DOCUMENT`; cada execução
lógica trata somente uma operação de uma fonte. A camada não seleciona
conectores, não cria plano, não agrega resultados e não altera lifecycle.

### Portas e tempo

Relógio monotônico, espera assíncrona, jitter e idempotência são Protocols
pequenos e injetáveis. O deadline absoluto do contexto disputa com a tarefa do
conector; expiração cancela e aguarda a tarefa, e seu outcome tardio é
descartado. Cancelamento cooperativo é verificado antes e depois de cada
fronteira que poderia publicar ou repetir conteúdo.

### Política, retry e budget

A política imutável e versionada limita tentativas a cinco, itens a 10.000,
artefatos a 100, backoff a uma hora e jitter a cinco minutos. Por padrão,
somente `RATE_LIMITED`, `TIMEOUT` e `UNAVAILABLE` podem repetir;
`INVALID_RESPONSE` e `INTERNAL_ERROR` exigem autorização explícita.

Quando há budget, uma estimativa tipada por tentativa é obrigatória na mesma
moeda. Ela é verificada antes da chamada; custo real substitui a estimativa e,
se ausente, a estimativa é contabilizada conservadoramente. Não há saldo
persistido, câmbio implícito ou conversão.

### Idempotência e representação segura

O fingerprint SHA-256 é construído por codificação explícita da semântica
pública, sem `repr`, payload, cursor, segredo, deadline ou estado transitório.
O adapter em memória é instance-scoped e atômico dentro de um processo: executa
uma vez, coordena concorrentes iguais sob o deadline de cada chamador, preserva
replay de sucesso/falha, rejeita colisão de `operation_id` e libera owner
cancelado.

O digest e os eventos contêm somente uma allowlist estrutural de IDs, versões,
operação, códigos, contagens, uso e hashes. Mensagens, query, candidato,
documento, cursor, credencial, conteúdo e stack são excluídos.

### Limites e validação

Cada tentativa realiza uma chamada e publica no máximo uma página. O menor
limite entre política e descritor é aplicado; truncamento e página adicional
viram `PARTIAL`, sem cursor. O runner valida outcome, itens, proveniência,
vínculos, paginação, status, mensagens, custo e digest antes de publicar.
Violação vira `INVALID_RESPONSE`; exceção externa vira `INTERNAL_ERROR`
redigido.

## Consequências

- Controles de uma chamada podem ser provados sem rede, persistência ou
  dependência nova.
- Replays não duplicam invocação ou accounting dentro da instância do store.
- Resultado da fonte continua separado do wrapper de controle.
- O store não oferece coordenação distribuída nem durabilidade.
- Jitter padrão zero e uma única página são limitações deliberadas da fase.
- Multi-conector, planner, jobs, filas, circuit breaker, rate limit global,
  persistência e lifecycle continuam decisões da Fase 4 ou posteriores.
- A aceitação deste ADR registra a arquitetura implementada, mas não constitui
  aceite independente da F3.3, do gate G3 ou autorização da Fase 4.
