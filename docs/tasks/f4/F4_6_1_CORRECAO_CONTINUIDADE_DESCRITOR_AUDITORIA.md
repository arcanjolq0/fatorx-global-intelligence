# F4.6.1 — Continuidade do descritor e auditoria concorrente

## Estado

**ACEITA APÓS NOVA REVISÃO INDEPENDENTE, EM CONJUNTO COM A F4.6.2.** A primeira
revisão confirmou a corrida F4.3 e a continuidade anterior ao I/O, mas encontrou
retry após divergência pós-tentativa. A F4.6.2 resolveu esse achado. O aceite não
fecha a Fase 4 nem autoriza subfases posteriores.

## Origem

A revisão independente do pacote F4.6 V2 exigiu uma F4.6.1 por dois achados:

- um conector mutável podia apresentar descritores diferentes entre a admissão,
  o ownership e o preflight do runner;
- comandos F4.3 distintos na mesma versão podiam ou não registrar a auditoria
  de conflito conforme o instante da disputa.

## Correções

- a aplicação usa um único `ConnectorPreflight` validado antes do commit como
  fonte do descritor comparado ao manifesto e persistido no ownership;
- após o commit, o runner refaz seu preflight e exige igualdade exata com o
  descritor persistido antes de reservar idempotência ou chamar o conector;
- descritor alterado nos preflights falha fechado, sem I/O, e deixa ownership
  sem conclusão, sujeito à futura recuperação ainda não autorizada;
- a confirmação F4.3 bloqueia a `Investigation` por linha depois do lock de
  comando; comandos distintos ficam serializados e o perdedor registra
  deterministicamente `STATE_VERSION_CONFLICT`.

## Limites preservados

Não foram adicionados recovery, lease, `FETCH_DETAILS`, paralelismo, jobs,
filas, workers, scheduler, outbox, fonte real, HTTP, evidência, claim factual,
risco, relatório, endpoint ou frontend.

## Critérios de aceite

- teste adversarial comprova que descritor mutável não alcança a operação;
- ownership contém exatamente o descritor admitido contra o manifesto;
- runner rejeita preflight posterior divergente antes de I/O;
- corrida F4.3 passa cinco vezes com um sucesso e uma falha auditada;
- suíte integral, migrations, tipos, lint, scanner e builds passam;
- nova revisão independente decide aceite ou exige correção adicional.
