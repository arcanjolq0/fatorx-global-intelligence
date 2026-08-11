# F4.2.1 — Correção de integridade da reconstituição

Status: **ACEITA APÓS REVISÃO INDEPENDENTE**
Data: 2026-08-01
Pré-condição: F4.1 **ACEITA APÓS REVISÃO INDEPENDENTE**

## Objetivo

Fechar a lacuna pela qual linhas de candidatos formalmente válidas podiam ser
reconstituídas sem comprovar que scores, cobertura, classificação, conflitos,
digests e ranking correspondiam ao conteúdo persistido e à política do lote.

Esta tarefa corrige somente a F4.2. A F4.3 permanece não autorizada.

## Causa raiz

Os contratos de avaliação já calculavam resultados canônicos no caminho de
criação, mas a leitura PostgreSQL reconstruía os objetos principalmente por
tipo, faixa, formato de digest e escopo. O `EntityCandidateRecord` não recebia o
snapshot da política nem o digest de entrada, portanto não conseguia refazer a
avaliação oficial. O lote também não recalculava `submission_digest` e
`evaluation_digest` nem reaplicava a ordenação oficial.

Além disso, a serialização do lote preservava a ordem recebida, embora essa
ordem não fosse persistida e o matching já fosse independente dela. Isso
tornava o digest de submissão impossível de reconstruir genericamente.

## Correção

- somente `NAME_NORMALIZATION_V1` é aceita pelo schema atual;
- `DimensionScore` valida dimensão, score, peso, contribuição,
  disponibilidade, conflito e semântica do código de explicação;
- cada candidato recebe explicitamente a política e o digest de entrada do
  lote durante criação ou reconstituição;
- `EntityCandidateInput` e `CandidateEvaluation` oficiais são reconstruídos e
  seus candidate/input/policy digests, total, cobertura, classificação,
  conflito, rank e digest são comparados;
- `CandidateSubmissionBatch` usa ordem canônica crescente de `candidate_key`
  apenas em sua serialização, tornando o digest reproduzível sem alterar o
  ranking nem a ordem do objeto recebido;
- o agregado oficial é reconstruído, exige chaves únicas, ranks contíguos e a
  ordem exata da função única de ranking, e recalcula o digest agregado;
- o mapper rejeita dimensões órfãs e converte qualquer inconsistência para
  `PersistenceDataError` seguro, sem corrigir dados.

## Compatibilidade e limites

Pesos, thresholds, scores, contribuições, conflitos, ranking e lifecycle V1 não
mudaram. A única mudança canônica é que a ordem de entrada deixou de influenciar
`CandidateSubmissionBatch.digest`; permutações do mesmo conjunto agora têm o
mesmo digest. Um lote preliminar F4.2 gravado com candidatos fora da ordem de
chave pode exigir saneamento ou nova submissão antes da leitura F4.2.1. Não há
migration ou backfill porque não existe ordem original armazenada que possa ser
reconstruída com segurança.

Não foram adicionados confirmação/rejeição humana, `Company`, `PLANNING`,
planner, conectores, jobs, filas, workers, API, evidência, claim, risco,
relatório, HTTP, I/O externo, dependência ou alteração de lockfile.

## Aceitação

- adulterações individuais e agregadas são rejeitadas fail-closed;
- escrita normal e round-trip continuam válidos;
- política desconhecida e normalização diferente de V1 são rejeitadas;
- migration `20260729_04` permanece byte a byte inalterada;
- resultados e comandos estão em
  `docs/validation/f4.2.1-persisted-evaluation-integrity.md`.
