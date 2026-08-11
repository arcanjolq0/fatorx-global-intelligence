# ADR 0019 — Confirmação humana e materialização de Company

- Status: aceito após revisão independente
- Data: 2026-08-01
- Decisores: responsáveis técnicos do Fator X Global Intelligence
- Substitui: nenhuma decisão anterior

## Contexto

A F4.2/F4.2.1 encerra em `WAITING_FOR_ENTITY_CONFIRMATION` com um lote imutável,
avaliado e reconstituído de forma fail-closed. Falta registrar a escolha humana
positiva sem transformar matching em decisão automática, sem mutar o candidato e
sem iniciar planejamento.

## Decisão

`ConfirmEntityCandidate` é o único comando novo. OWNER, ADMIN e ANALYST podem
selecionar um candidato do lote ativo; VIEWER não pode. `EXCLUDED` é sempre
bloqueado. `LOW` ou rank maior que 1 exige `MANUAL_OVERRIDE`.

A política fechada `COMPANY_MATERIALIZATION_V1` cria sempre uma nova `Company`.
Ela copia somente nome legal e comercial originais, país, data de constituição e
domínio normalizado. Forma jurídica e data de dissolução ficam nulas. Status de
origem ACTIVE/INACTIVE preserva a classe; DISSOLVED, UNKNOWN ou ausente vira
`CompanyStatus.UNKNOWN`, pois nenhuma data de dissolução pode ser inventada.
Os nomes canônicos preservam inclusive whitespace externo do valor original;
validação rejeita valor em branco, mas não o normaliza silenciosamente.

A decisão fica em `entity_resolution_decision`, append-only, com FKs tenant-scoped,
snapshot/digest da política, digests do lote/candidato/Company e unicidade por
investigação, comando e Company no workspace. O candidato continua
`PENDING_REVIEW`; ele não é atualizado.

Company, decisão, CAS da Investigation, ledger e auditoria de sucesso são gravados
em uma transação. O ledger referencia a decisão por FK diferida. O replay usa o
lock tenant-scoped de `command_id`, valida novamente todos os registros e não lê
relógio nem gera IDs. Um digest diferente para o mesmo comando é colisão tipada.

A transição única é
`WAITING_FOR_ENTITY_CONFIRMATION -> PLANNING`: preenche `confirmed_company_id`,
limpa `active_candidate_batch_id` e incrementa a versão uma vez. Entrar em
`PLANNING` não cria plano nem executa qualquer atividade de planejamento.

## Consequências

- confirmação é sempre humana e explícita; score nunca seleciona candidato;
- decisão e candidato não são evidência, claim, risco ou fato reportável;
- duas investigações podem criar duas Companies para a mesma entidade real;
  deduplicação, merge e vínculo com Company existente ficam fora da F4.3;
- downgrade recusa, com erro, banco que contenha decisão/ledger F4.3 ou
  `Company.status = UNKNOWN`, sem apagar histórico ou converter status;
- a autorização posterior da F4.4 não alterou a decisão de confirmação.

## Alternativas rejeitadas

- vincular Company existente por similaridade: associação silenciosa e não auditável;
- atualizar o candidato com a decisão: quebra o contrato append-only aceito da F4.2;
- confirmar automaticamente o rank 1: transfere decisão crítica ao score;
- commit intermediário: permitiria Company ou decisão órfã;
- mapear DISSOLVED sem data: violaria a invariante canônica de Company.

## Adendo F4.3.1 — replay ancorado no fato histórico

A confirmação já gravada é validada pela transição histórica que a criou, não
pela suposição de que o snapshot atual ainda esteja em `PLANNING`. A transição
continua obrigatoriamente `WAITING_FOR_ENTITY_CONFIRMATION -> PLANNING`, com
incremento unitário e correlação integral com decisão, comando e artefatos.

Separadamente, a Investigation atual deve manter a Company confirmada, lote
ativo nulo, versão maior ou igual à versão histórica e um estado autorizado
pós-confirmação. Se as versões forem iguais, o estado ainda deve ser `PLANNING`.
Assim, avanço e cancelamento não invalidam a decisão nem são revertidos pelo
replay. Registros parciais ou internamente divergentes são corrupção e falham
fechados; somente conflito contra histórico íntegro é colisão de comando.
