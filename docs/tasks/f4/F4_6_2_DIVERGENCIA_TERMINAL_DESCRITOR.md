# F4.6.2 — Divergência terminal do descritor

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE.** Esta correção é estritamente interna à
F4.6. O aceite não fecha a Fase 4 nem autoriza subfases posteriores.

## Motivação

A revisão independente da F4.6.1 confirmou a continuidade pré-I/O e a correção
concorrente F4.3, mas demonstrou que uma mudança do descritor após a primeira
tentativa era convertida em `INVALID_RESPONSE`. Quando esse código constava da
política de retry, duas novas operações podiam ocorrer após a divergência.

## Correção

- distinguir instabilidade do descritor de outras respostas inválidas;
- manter a conclusão pública redigida como `INVALID_RESPONSE`;
- tratar a instabilidade como terminal dentro do runner;
- nunca aplicar backoff, reservar outra tentativa ou executar novo I/O após a
  primeira divergência observada;
- preservar accounting e a conclusão da tentativa que já havia sido iniciada.

## Critérios de aceitação

- mutação nas chamadas de descritor anteriores ao ownership: zero operação;
- mutação nos preflights pós-commit: zero operação;
- mutação após a primeira tentativa: exatamente uma operação;
- política contendo `INVALID_RESPONSE` como retriável não altera esses limites;
- ownership, conclusão redigida, manifesto e fronteiras da F4.6 permanecem
  inalterados.

## Exclusões

Sem recovery, lease, operação adicional, paralelismo, jobs, filas, workers,
outbox, HTTP, conector real, evidência, claim factual, risco ou relatório.
