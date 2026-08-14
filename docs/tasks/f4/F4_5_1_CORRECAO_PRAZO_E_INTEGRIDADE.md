# F4.5.1 — Correção de prazo e integridade histórica da ativação

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE EM 2026-08-11.** Esta correção não
autorizava a F4.6 nem qualquer execução do manifesto. Essa autorização ocorreu
posteriormente, em instrução própria.

## Objetivo

Corrigir três lacunas da F4.5 sem alterar a política de planejamento nem as
durações persistidas:

- revalidar o tempo restante imediatamente antes da ativação;
- provar a correspondência exata entre `CollectionRun` e a transição histórica
  `PLANNING -> COLLECTING` em todas as leituras;
- produzir o artefato final com nomes internos POSIX e validação portátil.

## Contrato de prazo

O instante `activated_at` é lido uma única vez depois das cargas e validações
tenant-scoped e antes da geração de IDs. O caminho crítico é calculado sobre a
opção rank 1 que originaria cada operação de capacidade `READY`; capacidades
`OPTIONAL_UNAVAILABLE` não participam. A condição aceita é:

`activated_at + critical_path_duration <= investigation.deadline_at`

Igualdade é válida. Insuficiência gera `CollectionActivationDeadlineError` e
auditoria mínima de falha, mas não cria run, operação, transição, CAS, ledger ou
auditoria de sucesso.

## Contrato de integridade histórica

Toda reconstituição por comando, Investigation, plano ou ID exige uma transição
`START_COLLECTION` que coincida com o run em:

- workspace, Investigation, command ID e command digest;
- estados `PLANNING -> COLLECTING` e incremento unitário de versão;
- versão final da Investigation, ator e instante;
- run ID, Company, plano, política e quantidade de operações.

Ausência de qualquer lado ou divergência interna resulta em
`PersistenceDataError`. `InvestigationCommandCollisionError` fica restrito ao
caso em que o `command_id` já pertence a outro tipo de comando ou digest. Replay
íntegro em nova UoW devolve o mesmo run sem clock, IDs, CAS ou novas escritas.

## Persistência

A migration nova `20260802_09_harden_collection_activation_history.py` é
estritamente necessária porque a transição F4.5 original não armazenava os IDs
de Company e plano. Ela:

- adiciona `collection_company_id` e `collection_plan_id` à transição;
- preenche linhas F4.5 existentes a partir do run já ligado por FK;
- amplia a completude da metadata de quatro para seis campos;
- reforça a FK composta para exigir o mesmo run, workspace, Investigation,
  Company e plano;
- mantém downgrade reversível para a revisão `20260802_08`.

Nenhuma migration anterior foi alterada, nenhuma dependência ou lockfile foi
adicionado e nenhuma tabela nova foi criada.

## Fora do escopo

Não há execução de conector ou runner F3.3, retry, timeout operacional, job,
fila, worker, scheduler, outbox, resultado, HTTP, API, frontend, evidência,
claim, risco ou relatório. Run e operações continuam preparação persistente em
`PENDING`.
