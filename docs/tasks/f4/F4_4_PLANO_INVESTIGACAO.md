# F4.4 — Plano determinístico de investigação

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE, INCLUINDO A F4.4.1.** A Fase 4
continua em andamento. A F4.5 não está autorizada.

A correção F4.4.1 preserva a leitura e o replay após avanço do lifecycle,
calcula prazo somente sobre capacidades `READY` e adiciona a migration
`20260801_07` para reforçar o custo tipado da auditoria. O contrato original de
criação do plano e a ausência de execução permanecem inalterados.

## Objetivo e fluxo

`CreateInvestigationPlan` cria o único plano imutável de uma Investigation que
já esteja em `PLANNING` e possua `confirmed_company_id`. O resultado fica
`READY`; a Investigation permanece em `PLANNING`, sem mudança de
`state_version`.

O comando contém somente `command_id`, `investigation_id`, versão esperada e
política fechada. Plano pronto, conectores escolhidos, estado destino, custo e
digests não são aceitos do cliente.

## Política V1

`INVESTIGATION_PLANNING_V1` suporta `SUPPLIER_STANDARD` e as dez capacidades do
enum atual. `COMPANY_IDENTITY` e `COMPANY_REGISTRY` são obrigatórias; as demais
são opcionais. `OWNERSHIP` depende de `COMPANY_REGISTRY`, o grafo é acíclico e
toda referência deve existir no plano.

Elegibilidade usa exclusivamente Company/Investigation persistidas e descritores
imutáveis capturados na admissão do registro explícito. A ordem é:

1. cobertura `COUNTRY_SET` contendo o país antes de `GLOBAL`;
2. contrato corrente antes de outra versão compatível de mesmo major;
3. custo estático, quando o contrato de descritor vier a oferecê-lo;
4. `connector_id` crescente.

O descritor F3 atual não contém preço. A F4.4 registra `EstimatedCostKind.UNKNOWN`
e valor nulo; não inventa custo. Cada capacidade tem duração estática V1 de uma
hora, e o deadline é validado pelo caminho crítico do grafo usando o instante
injetado pelo serviço.

## Persistência e transação

A migration `20260801_06` cria:

- `investigation_plan`;
- `planned_capability`;
- `planned_connector_option`.

As tabelas usam FKs compostas tenant-scoped, unicidades por Investigation,
comando, capacidade, conector e rank, checks fechados de versão/status/digest,
`NUMERIC` para dinheiro e arrays tipados para dependências/operações. O snapshot
canônico da política é texto fechado versionado, não JSONB genérico. Não existe
update/delete público.

O fluxo é autorização, advisory lock do comando, replay/collision, lock da
Investigation, leitura tenant-scoped da Company, geração pura, persistência do
agregado, auditoria e commit único. Como não há transição, não se cria linha em
`investigation_transition`; `command_id` e `command_digest` do próprio plano são
o registro durável desse comando.

## Idempotência e autorização

OWNER, ADMIN e ANALYST podem criar; VIEWER é negado. Mesmo comando e digest
devolve o plano com `replayed=True`, sem relógio, IDs, registros ou nova
auditoria. Mesmo ID com conteúdo divergente gera
`InvestigationCommandCollisionError`. Comandos distintos para a mesma
Investigation são serializados pelo lock da linha; apenas um plano é criado e o
perdedor recebe `InvestigationPlanAlreadyExistsError`.

## Limites deliberados

A F4.4 não chama conectores nem consulta disponibilidade, rede, credenciais ou
ambiente. Não cria seleção operacional, execução, jobs, filas, workers, runs,
outbox, HTTP, fontes reais, upload, OCR, evidência, claim, risco, score de
crédito, limite, relatório, endpoint ou frontend. Capacidades futuras de
pagamento, comércio exterior e regularidade fiscal permanecem apenas no backlog.
