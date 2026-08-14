# Revisão do gate da Fase 4 e handoff para a Fase 5

## Veredito e decisão

**O GATE HISTÓRICO NÃO FOI DECLARADO SATISFEITO.** O responsável aceitou em
2026-08-14 a separação do ADR 0023: a Fase 4 foi concluída exclusivamente no
Gate F4-F; o Gate E2E permanece aberto e obrigatório antes do piloto; somente a
F5.1 foi autorizada.

## Evidência revisada

A revisão confrontou `PLANS.md`, `docs/investigation-lifecycle.md`, o roadmap da
F4, os ADRs aceitos e o código executável no checkpoint `3bd2077`. A validação
técnica mais recente aprovou 1.345 testes Python, cobertura branch de 89,59%,
Vitest, lint, tipos, scanner e builds; isso comprova as entregas aceitas, não as
capacidades ausentes.

## Matriz do gate

| Critério | Estado | Evidência ou lacuna |
|---|---|---|
| lifecycle transacional até `COLLECTING` | comprovado | F4.1, F4.2, F4.3 e F4.5 aceitas |
| resolução de homônimos e confirmação humana | comprovado | matching versionado, pausa e confirmação explícita |
| isolamento, concorrência, idempotência e auditoria | comprovado no corte | revisões independentes e testes PostgreSQL |
| plano e manifesto determinísticos | comprovado | F4.4/F4.5 aceitas |
| uma execução simulada controlada | comprovado | F4.6/F4.6.1/F4.6.2 aceitas |
| fan-out/fan-in e consolidação de falhas | ausente | explicitamente não autorizado após F4.6 |
| recovery/lease e retomada operacional | ausente | ownership órfão permanece fail-closed |
| fechamento `COLLECTING -> NORMALIZING` | ausente | `CloseCollection` é apenas alvo documental |
| revisão geral e retorno à análise | ausente | depende de claims e avaliação |
| `COMPLETED`/`PARTIALLY_COMPLETED` | ausente | depende de evidência, risco, relatório e aprovação |

## Contradição encontrada

O critério histórico da F4 exige conclusão parcial determinística. O contrato do
lifecycle, corretamente, só permite conclusão parcial quando existe evidência
admissível, lacunas publicadas, avaliação aplicável, relatório e aceite humano.
Esses elementos são entregáveis das Fases 5–7. Portanto:

- aceitar o gate agora seria falso;
- implementar conclusão antes da F5 violaria a regra de evidência;
- impedir a F5 até a conclusão manteria um ciclo impossível.

## Plano recomendado

### Decisão 1 — aceitar o ADR 0023 — concluída

Aceitar a separação proposta entre o Gate F4-F de fundação e o Gate E2E
transversal. Esta etapa é documental e não autoriza código.

### Decisão 2 — fechar a Fase 4 no Gate F4-F — concluída

Atualizar o estado para “Fase 4 concluída no Gate F4-F”, preservando como
limitações explícitas todas as capacidades posteriores a `COLLECTING`. Não
renomear resultados operacionais como evidência ou claims.

### Decisão 3 — autorizar somente a F5.1 — concluída

Planejar o núcleo canônico de evidências: identidade, proveniência, hash,
localização, política, imutabilidade, revogação/versionamento e porta de
persistência. A F5.1 não deve executar conectores, consumir HTTP, criar claims,
calcular risco, produzir relatório ou avançar o lifecycle.

### Decisão 4 — manter um Gate E2E explícito — vigente

Antes do piloto, provar com simuladores o caminho completo, inclusive fechamento
da coleta, normalização, claims, avaliação, revisão humana, conclusão total e
parcial, cancelamento tardio e recuperação operacional.

## Limites

Esta revisão não implementa F4.7, recovery, lease, jobs, filas, workers,
paralelismo, operações adicionais, HTTP, fontes reais, evidência, claims, risco
ou relatório. O ADR 0023 está `Accepted`; a autorização subsequente alcança
somente a F5.1 e não promove o Gate E2E.
