# F4.4.1 — Correção da continuidade histórica do plano

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE.** A F4.5 foi autorizada e implementada
posteriormente; a F4.6 permanece não autorizada.

## Objetivo

Corrigir três inconsistências da F4.4 sem criar execução de plano ou nova
transição de lifecycle:

1. preservar a leitura e o replay do plano imutável quando a Investigation
   avança além de `PLANNING`;
2. excluir capacidades `OPTIONAL_UNAVAILABLE` do cálculo de prazo;
3. tornar atômico o conjunto tipado de custo da auditoria de planejamento.

## Continuidade do plano

O contexto histórico continua válido quando a Company confirmada é a mesma, o
lote ativo permanece nulo, a versão atual não é inferior à versão de criação do
plano e o estado atual é `PLANNING`, `COLLECTING`, `NORMALIZING`, `VERIFYING`,
`ANALYZING`, `WAITING_FOR_REVIEW`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`
ou `CANCELLED`. Se a versão ainda é exatamente a versão de criação, o estado
deve continuar sendo `PLANNING`.

Estados anteriores à confirmação, regressão de versão, troca de Company ou
reintrodução de lote ativo falham fechados. Essa regra é aplicada pela
reconstituição compartilhada de `get_by_command`, `get_by_investigation` e
`get_by_id`; o replay não restaura estado nem produz nova escrita.

## Prazo e caminho crítico

O cálculo do caminho crítico considera somente capacidades `READY`, pois são as
únicas executáveis no plano atual. Capacidades `OPTIONAL_UNAVAILABLE` continuam
persistidas e explicadas, mas não consomem deadline. Prioridades, dependências,
política e seleção determinística de conectores não mudaram.

## Persistência

A migration `20260801_07` sucede `20260801_06` sem alterá-la. Ela substitui o
check de consistência de custo da auditoria para aceitar somente:

- comando e campos de custo todos ausentes;
- comando presente, kind `UNKNOWN` e par valor/moeda ausente;
- comando presente, kind `KNOWN` e par valor/moeda completo.

O downgrade restaura exatamente a expressão da F4.4. Dados parciais existentes
fazem o upgrade falhar fechado; a migration não fabrica correção de auditoria.

## Fora do escopo

Não foram adicionados execução de conectores, avanço para `COLLECTING`, jobs,
filas, workers, runs, API, frontend, evidências, claims, risco ou relatórios.
Não houve dependência ou lockfile novo.
