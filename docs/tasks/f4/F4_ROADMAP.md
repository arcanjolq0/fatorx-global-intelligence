# Fase 4 — Orquestração e resolução de entidades

## Estado

- Fase 3 e gate G3: **CONCLUÍDOS E ACEITOS**;
- F4.1: **ACEITA APÓS REVISÃO INDEPENDENTE**;
- F4.2/F4.2.1: **ACEITAS APÓS REVISÃO INDEPENDENTE**;
- F4.3/F4.3.1: **ACEITAS APÓS REVISÃO INDEPENDENTE**;
- F4.4/F4.4.1: **ACEITAS APÓS REVISÃO INDEPENDENTE**;
- F4.5/F4.5.1: **ACEITAS APÓS REVISÃO INDEPENDENTE**;
- F4.6/F4.6.1/F4.6.2: **ACEITAS APÓS REVISÃO INDEPENDENTE**;
- subfases posteriores: **NÃO AUTORIZADAS**.

A revisão de fechamento concluiu que o gate histórico não está satisfeito. O
ADR 0023 foi aceito em 2026-08-14: a Fase 4 está **CONCLUÍDA EXCLUSIVAMENTE NO
GATE F4-F**; o Gate E2E permanece aberto e obrigatório antes do piloto. Somente
a F5.1 foi autorizada. Este roadmap não autoriza qualquer outro avanço.

## F4.1 — Lifecycle transacional inicial

A fundação aceita materializa entrada de identificação imutável,
`CREATED -> IDENTIFYING`, cancelamento de estado não terminal, CAS tenant-scoped,
idempotência durável, ledger append-only e auditoria coordenada.

## F4.2 — Candidatos, matching e pausa para confirmação

Esta entrega materializa exclusivamente:

- lote explícito de um a 100 candidatos imutáveis e não confiáveis;
- identidade e origem fechadas, versionadas e acompanhadas por digests;
- política `ENTITY_MATCH_V1` reconstruível por snapshot e digest;
- normalização Unicode NFKC, `casefold`, substituição de pontuação/símbolos por
  espaço e colapso de whitespace, sem transliteração;
- sete dimensões determinísticas: identificador, nome, domínio, geografia,
  endereço, administradores e temporal;
- conflitos fortes por identificador comparável divergente e país divergente;
- score inteiro em basis points, cobertura dos pesos disponíveis, explicações e
  ranking estável;
- lote, candidatos e scores dimensionais append-only e tenant-scoped;
- `RequestEntityConfirmation`, apenas de `IDENTIFYING` para
  `WAITING_FOR_ENTITY_CONFIRMATION`;
- CAS, replay/collision, ledger, auditoria e persistência do lote no mesmo commit;
- migration `20260729_04`, reversível e sucessora da F4.1.

Os pesos V1 são: identificador 3500, nome 2500, domínio 1200, geografia 1000,
endereço 800, administradores 700 e temporal 300. `HIGH` exige 8500 bps,
`MEDIUM` exige 6000 bps, abaixo disso é `LOW`; conflito forte resulta em
`EXCLUDED` independentemente do score.

Score mede compatibilidade segundo a política, não probabilidade, crédito ou
risco. Cobertura mede a soma dos pesos das dimensões comparáveis; ausência de
dado não é confirmação. Candidato não é empresa canônica, evidência ou claim e
nenhum candidato foi confirmado nesta entrega.

### Correção F4.2.1

A reconstituição agora recalcula política, candidatos, dimensões, avaliações,
submission digest, digest agregado e ranking, falhando fechado diante de
qualquer inconsistência. Somente `NAME_NORMALIZATION_V1` é suportada. A ordem
canônica do submission digest é por `candidate_key`; matching, pesos,
thresholds, tabelas, migration e lifecycle não mudaram.

## F4.3 — Confirmação humana e Company canônica

A F4.3 implementa exclusivamente a decisão humana positiva: valida o lote ativo,
bloqueia `EXCLUDED`, aplica regras fechadas de override, cria nova Company pela
política V1, persiste decisão append-only e avança para `PLANNING` no mesmo
commit. Não escolhe por score, não vincula Company existente e não cria plano.

### Correção F4.3.1

O replay agora ancora a confirmação na transição histórica imutável
`WAITING_FOR_ENTITY_CONFIRMATION -> PLANNING`, com versão, comando, digest,
decisão, Company, lote, candidato, políticas e timestamp correlacionados. O
snapshot atual é validado separadamente e pode ter avançado ou sido cancelado,
desde que preserve a Company confirmada, mantenha o lote ativo nulo e tenha
versão não inferior à transição. O mesmo comando íntegro é apenas devolvido:
não há relógio, novos IDs, CAS, restauração de estado, ledger ou auditoria nova.
Persistência parcial ou internamente divergente falha fechada; colisão permanece
reservada a conflito semântico contra histórico íntegro.

A correção não criou migration, dependência, lockfile, transição ou capacidade
nova. A F4.4 foi autorizada posteriormente por instrução específica.

## F4.4 — Plano determinístico de investigação

A F4.4 persiste um único plano `READY` por Investigation em `PLANNING`, sem
alterar estado ou `state_version`. A política `INVESTIGATION_PLANNING_V1` usa a
Company confirmada, perfil, país, orçamento/deadline e cópias imutáveis dos
descritores admitidos no registro explícito. Ela não chama conectores.

As dez capacidades existentes são representadas, com indisponibilidade opcional
explícita. Registro e identidade empresarial são obrigatórios; `OWNERSHIP`
depende de `COMPANY_REGISTRY`. A migration `20260801_06` cria
`investigation_plan`, `planned_capability` e `planned_connector_option`, com FKs
tenant-scoped, unicidades, checks fechados e downgrade que recusa apagar planos.

### Correção F4.4.1

A continuidade histórica aceita o plano após avanço para os estados
pós-confirmação autorizados, desde que Company e contexto imutável sejam
preservados, o lote ativo continue nulo e a versão não regrida. As três leituras
e o replay usam a mesma validação fail-closed. Capacidades
`OPTIONAL_UNAVAILABLE` permanecem no plano, mas somente `READY` participa do
caminho crítico. A migration `20260801_07` torna atômico o conjunto tipado de
custo da auditoria, sem modificar a migration F4.4.

## F4.5 — Ativação do plano e manifesto de coleta

A F4.5 cria `CollectionRun` e uma `CollectionOperation` para cada capacidade
`READY`, selecionando exclusivamente a opção persistida rank 1. Dependências
são convertidas para operações do mesmo run. O manifesto é append-only,
tenant-scoped e inicia em `PENDING`; não representa job nem resultado.

O serviço avança somente `PLANNING -> COLLECTING` com CAS, ledger e auditoria no
mesmo commit. Replay íntegro não lê clock, gera IDs, executa CAS ou escreve. A
migration `20260802_08` cria as três tabelas de manifesto e FKs compostas.
Registry, simuladores, runner e conectores não são chamados.

### Correção F4.5.1

A ativação revalida o deadline com o caminho crítico das operações derivadas
somente de capacidades `READY`, aceitando igualdade e rejeitando insuficiência
antes de materializar o run. Toda leitura correlaciona o run com a transição
histórica exata, inclusive ator, instante, Company e plano. A migration
`20260802_09` adiciona apenas os dois vínculos históricos necessários. A F4.6
foi autorizada e implementada posteriormente em entrega própria.

## F4.6 — Execução direta controlada

A F4.6 consome uma única operação `SEARCH` do manifesto por comando. O conector
é fornecido explicitamente, allowlisted, precisa corresponder ao snapshot e só
opera em `TEST`. Um ownership tenant-scoped é persistido antes do I/O; a conclusão
posterior contém somente outcome, accounting e digests, nunca itens/payload.

O manifesto não muda de status. Não há jobs, filas, workers, descoberta,
paralelismo, `FETCH_DETAILS`, fonte real ou transição de lifecycle. A migration
`20260811_10` cria as duas tabelas append-only. A implementação aguarda revisão
independente; detalhes estão em `F4_6_EXECUCAO_DIRETA_CONTROLADA.md`.

## F4.6.1 — Continuidade do descritor e auditoria concorrente

O descritor do preflight pré-commit passa a ser a única fonte do ownership e o
runner exige igualdade no preflight pós-commit antes de I/O. Comandos F4.3
distintos são serializados pelo lock da Investigation, tornando a falha de
versão e sua auditoria determinísticas. A correção não expande a funcionalidade
e foi aceita em conjunto com a F4.6.2 após nova revisão independente.

## F4.6.2 — Divergência terminal do descritor

Uma mudança de descritor observada após a operação é distinta de uma resposta
externa inválida e encerra a execução lógica imediatamente. O resultado redigido
pode registrar a falha da tentativa já iniciada, mas a política de retry não
pode reservar nem executar outra tentativa. O teste adversarial cobre mutações
antes do ownership, nos preflights pós-commit e após a primeira tentativa com
`INVALID_RESPONSE` explicitamente retriável.

## Exclusões e próximas subfases

Não foram implementados:

- rejeição de candidato ou de todos os candidatos;
- associação, deduplicação ou merge de `Company`;
- qualquer transição posterior a `COLLECTING`;
- descoberta dinâmica, conector real ou operação além de um `SEARCH` direto;
- recovery/lease, jobs, filas, workers, outbox ou fan-out/fan-in;
- evidência, claim factual, risco, relatório, endpoint ou frontend novo.

Esses itens posteriores à F4.6 exigem instrução e revisão próprias. Conectores
reais continuam condicionados ao gate G6 e às aprovações técnica, jurídica e
comercial por fonte.

## Gate da Fase 4

A revisão formal está em `F4_GATE_REVIEW_AND_F5_HANDOFF.md`. Isolamento,
concorrência, idempotência, resolução de homônimos, confirmação humana e uma
execução simulada controlada estão comprovados. Fan-out, recovery, fechamento
da coleta, revisão geral e conclusão parcial não estão implementados.

O critério histórico exige lifecycle completo, mas suas transições finais
dependem de evidências, claims, risco e relatório das Fases 5–7. O ADR 0023
`Accepted` separa a fundação F4-F do Gate E2E transversal. O Gate F4-F está
aceito; o Gate E2E não está e não pode ser silenciosamente promovido.
