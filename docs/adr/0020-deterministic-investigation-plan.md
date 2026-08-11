# ADR 0020 — Política e persistência do plano determinístico

- Status: aceito após revisão independente, incluindo a correção F4.4.1
- Data: 2026-08-02
- Decisores: responsáveis técnicos do Fator X Global Intelligence
- Substitui: nenhuma decisão anterior

## Contexto

A F4.3/F4.3.1 termina com Company confirmada e Investigation em `PLANNING`.
Era necessário registrar, de forma reproduzível, o que uma coleta futura deverá
cobrir, sem executar conectores, depender de disponibilidade externa ou avançar
o lifecycle.

## Decisão

Adotar `INVESTIGATION_PLANNING_V1`, política pura e reconstruível por snapshot
canônico e SHA-256. Ela consome somente Investigation, Company e descritores
estáticos admitidos no `ConnectorRegistry`. O registro expõe cópias capturadas
dos descritores; planejamento nunca invoca métodos de conector.

As capacidades usam o enum aceito da F3. Identidade e registro são required;
demais capacidades são optional e ficam `OPTIONAL_UNAVAILABLE` quando não há
opção. `OWNERSHIP` depende de `COMPANY_REGISTRY`. Uma required sem opção falha
fechado. Ranking privilegia cobertura exata do país, contrato corrente e ID
estável. O contrato atual não contém preço; custo é `UNKNOWN` tipado.

Persistir o agregado em `investigation_plan`, `planned_capability` e
`planned_connector_option`. Os registros são append-only pela porta pública,
tenant-scoped e integralmente reconstituídos. Política, Company, input e plano
possuem digests correlacionados. A linha raiz contém comando/digest e funciona
como registro durável do comando; não há ledger de transição porque a
Investigation permanece em `PLANNING` e sua versão não muda.

Autorizar OWNER, ADMIN e ANALYST; negar VIEWER. A transação única inclui plano,
filhos e auditoria allowlisted. Replay íntegro não lê clock, não gera IDs e não
duplica auditoria. Comandos distintos são serializados pelo lock da
Investigation e pela unicidade de um plano por investigação.

A F4.4.1 esclarece que a imutabilidade é histórica: a reconstituição do plano
continua válida após avanço do snapshot atual para estados pós-confirmação,
desde que Company, ausência de lote ativo e monotonicidade da versão sejam
preservadas. Na versão original, `PLANNING` permanece obrigatório. A correção
também exclui `OPTIONAL_UNAVAILABLE` do caminho crítico e fortalece o check do
conjunto tipado de custo da auditoria na migration sucessora `20260801_07`.

## Consequências

- o plano é reproduzível a partir de snapshots persistidos e falha fechado sob
  adulteração;
- ausência de preço não é convertida em zero nem em estimativa fictícia;
- orçamento só pode ser comparado quando custos vierem a ser conhecidos;
- prazo V1 é uma estimativa estática de planejamento, não SLA nem observação de
  disponibilidade;
- downgrade recusa apagar plano existente;
- plano não é evidência, claim, avaliação de risco ou relatório;
- a F4.5 passou a consumir o plano aceito sem alterar suas decisões históricas.

## Alternativas rejeitadas

- consultar saúde/disponibilidade externa: introduziria I/O e não determinismo;
- escolher somente um conector: perderia alternativas elegíveis e anteciparia
  decisão operacional;
- gravar plano em JSONB único: enfraqueceria FKs, unicidades e checks;
- usar `investigation_transition` sem mudança de estado: fabricaria um evento de
  lifecycle inexistente;
- avançar para `COLLECTING`: expandiria silenciosamente o escopo para F4.5.
