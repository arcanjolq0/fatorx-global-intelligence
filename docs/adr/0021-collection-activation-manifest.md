# ADR 0021 — Ativação transacional e manifesto imutável de coleta

- Status: aceito após revisão independente da F4.5.1
- Data: 2026-08-02
- Decisores: responsáveis técnicos do Fator X Global Intelligence
- Depende de: ADR 0016 e ADR 0020

## Contexto

A F4.4/F4.4.1 deixa uma Investigation em `PLANNING` com Company confirmada e
um plano `READY`, imutável e tenant-scoped. A ativação precisa congelar a
seleção operacional que uma fase futura poderá consumir, sem consultar
novamente o registry e sem chamar conector, runner, fila ou worker.

## Decisão

Adotar a política reconstruível `COLLECTION_ACTIVATION_V1`, que seleciona
exclusivamente a opção já persistida com `eligibility_rank == 1` para cada
capacidade `READY`. Capacidades `OPTIONAL_UNAVAILABLE` permanecem somente no
plano. Qualquer digest, rank, dependência, ciclo ou vínculo divergente falha
fechado.

Persistir um `CollectionRun` e suas `CollectionOperation` em
`collection_run`, `collection_operation` e
`collection_operation_dependency`. O manifesto copia os campos necessários
do plano, conserva orçamento/deadline, registra política, comando, contexto e
SHA-256, inicia run/operações em `PENDING` e tentativa zero. As portas públicas
são append-only.

O serviço executa autorização, lock de `command_id`, replay/collision, carga
tenant-scoped, validação, materialização, CAS, ledger e auditoria em uma única
transação. O único avanço é `PLANNING -> COLLECTING`, com incremento unitário de
`state_version`. Replay íntegro não lê clock, não gera IDs, não faz CAS e não
acrescenta auditoria.

A correção F4.5.1 revalida no instante de ativação se o caminho crítico das
operações derivadas somente de capacidades `READY` ainda cabe no deadline. Cada
run passa a exigir a transição histórica exata, correlacionada também por ator,
instante, Company e plano. A migration sucessora `20260802_09` persiste os dois
últimos vínculos sem alterar `20260802_08`.

OWNER, ADMIN e ANALYST podem ativar; VIEWER não. Auditoria registra somente IDs,
quantidade de operações, política, custo agregado tipado, resultado e
correlação.

## Consequências

- a decisão rank 1 é reproduzível sem disponibilidade externa;
- o manifesto não é job, resultado, evidência, claim, risco ou relatório;
- um run por Investigation e plano é protegido por unicidade e FKs compostas;
- reconstituição histórica continua válida após avanço compatível, mas nunca
  restaura nem executa estado;
- downgrade recusa apagar histórico de coleta existente;
- F4.6 continua necessária para qualquer execução e não está autorizada.

## Alternativas rejeitadas

- consultar novamente o registry: permitiria drift depois do plano;
- aceitar conector/operação do cliente: quebraria determinismo e autorização;
- executar o runner F3.3: excederia F4.5 e criaria efeitos operacionais;
- armazenar um JSONB opaco: enfraqueceria vínculos, unicidade e checks;
- avançar além de `COLLECTING`: anteciparia fases não autorizadas.
