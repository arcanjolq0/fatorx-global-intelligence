# ADR 0023 — Gate da Fase 4 e handoff para evidências

- Status: Accepted
- Data: 2026-08-14
- Decisores: responsáveis técnicos do Fator X Global Intelligence
- Depende de: ADR 0003, ADR 0006, ADR 0022

## Contexto

A F4.1 até a F4.6/F4.6.1/F4.6.2 foi aceita após revisões independentes. O corte
implementado alcança `COLLECTING`, confirma identidade, cria plano e manifesto e
executa diretamente um `SEARCH` sintético com ownership durável e conclusão
redigida.

O critério histórico de saída da Fase 4 também exige retomada geral e conclusão
parcial. O lifecycle completo, porém, condiciona esses estados a evidência
admissível, claims verificados, avaliação determinística, relatório e aprovação
humana. Essas capacidades pertencem às Fases 5, 6 e 7. Exigir sua implementação
antes de iniciar a Fase 5 cria uma dependência circular; removê-las
silenciosamente do gate reduziria um contrato aceito.

## Decisão

Separar dois marcos:

1. **Gate F4-F — fundação de orquestração e resolução:** termina em um handoff
   íntegro a partir de `COLLECTING`. Exige identidade confirmada, planejamento,
   manifesto, execução simulada controlada, isolamento, concorrência,
   idempotência, auditoria e limites explícitos. Não afirma investigação ponta a
   ponta nem conclusão parcial.
2. **Gate E2E — lifecycle completo:** permanece obrigatório antes do piloto e
   comprova fechamento da coleta, normalização, evidências, claims, risco,
   revisão e estados terminais. É um gate transversal às Fases 4–7.

Com essa separação, o aceite já obtido de F4.1–F4.6.2 satisfaz tecnicamente o
Gate F4-F. A Fase 5 pode ser autorizada em subfases próprias, começando pelo
núcleo de evidência sem integração real. O Gate E2E não é dispensado, apenas
reposicionado para quando suas dependências existirem.

## Consequências

- a Fase 4 pode ser fechada sem alegar capacidades inexistentes;
- a F5.1 pode começar sem jobs, workers, conectores reais ou relatório;
- transições posteriores a `COLLECTING` continuam não implementadas;
- conclusão parcial continua bloqueada até evidência, claims, risco, relatório e
  aprovação humana estarem materializados;
- a mudança exige aceite explícito deste ADR e atualização coordenada dos gates
  em `PLANS.md`, roadmap, lifecycle e critérios do MVP.

## Alternativas rejeitadas

- **declarar o gate atual satisfeito:** ocultaria lacunas comprovadas;
- **implementar placeholders para estados finais na F4:** permitiria conclusão
  sem evidência, claims, risco ou relatório;
- **bloquear a F5 até o lifecycle completo:** mantém a dependência circular;
- **mover toda a evidência para a F4:** mistura fronteiras e invalida a sequência
  documental das fases.

## Aceite

O responsável pelo projeto aceitou explicitamente em 2026-08-14 a separação
entre F4-F e E2E, encerrou a Fase 4 exclusivamente no Gate F4-F e autorizou
somente a F5.1. O Gate E2E permanece aberto e obrigatório antes do piloto.
