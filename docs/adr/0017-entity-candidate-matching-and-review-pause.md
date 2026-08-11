# ADR-0017 — Matching determinístico de candidatos e pausa para revisão

- Status: `Accepted`
- Data: 2026-07-29
- Decisão anterior relacionada: ADR-0016

## Contexto

A F4.1, aceita após revisão independente, fornece entrada congelada, comandos
fechados, CAS, idempotência durável, ledger e auditoria no mesmo commit. A F4.2
precisa avaliar candidatos fornecidos explicitamente e pausar a investigação
para decisão humana sem confirmar identidade, criar empresa ou iniciar planner.

Nome semelhante isoladamente não é vínculo confiável. O resultado precisa ser
reproduzível, explicável, tenant-scoped e reconstruível mesmo após mudança da
política corrente. Candidatos e payloads são dados não confiáveis e não são
evidência, claim ou fato canônico.

## Decisão

### Contratos e fronteiras

Criamos o pacote puro `intelligence.entity_resolution`, sem I/O, relógio,
aleatoriedade, conectores ou persistência. Ele recebe `IdentificationInput`, um
`CandidateSubmissionBatch` fechado e uma `MatchPolicy`, e retorna uma avaliação
imutável. A aplicação coordena persistência e lifecycle; infraestrutura apenas
implementa as portas.

O schema 1 de `IdentificationInput` permanece byte a byte compatível. O schema 2
é opt-in e adiciona somente administradores e data de constituição, necessários
para tornar comparáveis as dimensões `ADMINISTRATORS` e `TEMPORAL`. Ambos são
versionados, validados e incluídos no digest canônico.

### Política V1

A política `ENTITY_MATCH_V1`, versão 1, usa somente inteiros em basis points:

| Dimensão | Peso |
|---|---:|
| `IDENTIFIER` | 3500 |
| `NAME` | 2500 |
| `DOMAIN` | 1200 |
| `GEOGRAPHY` | 1000 |
| `ADDRESS` | 800 |
| `ADMINISTRATORS` | 700 |
| `TEMPORAL` | 300 |

`HIGH` começa em 8500, `MEDIUM` em 6000 e valores inferiores são `LOW`.
Identificador comparável divergente e país divergente são conflitos fortes e
classificam o candidato como `EXCLUDED`, sem apagar os scores explicativos.

Normalização de texto usa Unicode NFKC, `casefold`, troca de pontuação e símbolos
por espaço e colapso de whitespace. Não há transliteração, fuzzy library,
floating point, modelo ou conhecimento externo. Nome legal exato vale 10000,
nome comercial exato 9500, cruzamento entre os dois 9000 e conjunto de tokens
igual 8000. Administradores usam Jaccard inteiro; endereço compara componentes;
identificador, domínio, país e data usam regras fechadas.

O total é a soma inteira de `score * peso / 10000`. Cobertura é a soma dos pesos
das dimensões disponíveis. Ranking ordena conflito forte, classificação, score,
cobertura e score de identificador em ordem decrescente, seguido pela chave
estável do candidato em ordem crescente. A política completa, sua versão e seu
digest são persistidos; não dependemos apenas da constante atual do código.

### Transação e persistência

`RequestEntityConfirmation` autoriza somente
`IDENTIFYING -> WAITING_FOR_ENTITY_CONFIRMATION`, incrementa `state_version` uma
vez e associa um lote ativo. O serviço valida ator/permissão/tenant, replay ou
colisão, versão e digest da entrada; calcula o matcher puro; executa CAS; grava
lote, candidatos, dimensões, ledger e auditoria; e faz um único commit. O mesmo
comando e digest retorna o ledger sem ler relógio, gerar ID ou recalcular.

A migration `20260729_04` cria `entity_candidate_batch`, `entity_candidate` e
`entity_candidate_dimension_score`, acrescenta metadados fechados ao ledger e à
auditoria e adiciona `active_candidate_batch_id` à investigação. FKs compostas
preservam workspace. Snapshots JSONB são envelopes fechados e versionados, não
substituem o modelo relacional. Decisão permanece obrigatoriamente
`PENDING_REVIEW`; não existem operações de update/delete na porta.

A constraint que exige lote ativo no estado de espera é `NOT VALID` para não
inventar lote em linha histórica criada antes da F4.2; novas gravações são
verificadas. O domínio aceita somente snapshots coerentes, portanto uma linha
histórica inconsistente precisa ser saneada antes de reconstituição.

## Consequências

- Matching e ranking são reproduzíveis por política, entrada e candidatos.
- Ausência de dimensão reduz cobertura e nunca é tratada como confirmação.
- CAS vencedor determina o único lote; perdedores não deixam órfãos.
- Falha após CAS é revertida com lote, scores, estado, ledger e auditoria.
- O schema 2 da entrada é uma extensão explícita; consumidores do schema 1 não
  mudam silenciosamente.
- A retenção dos snapshots empresariais ainda precisa de política operacional.

## Alternativas rejeitadas

- Similaridade de nome como decisão: insuficiente para homônimos.
- Fuzzy matching ou biblioteca nova: aumentaria opacidade e dependência sem
  necessidade para a política inicial.
- Float ou probabilidade: prejudicaria reprodutibilidade entre runtimes.
- Referenciar somente a versão corrente da política: impediria reconstrução.
- Confirmar automaticamente o topo: violaria revisão humana e anteciparia F4.3.
- Chamar conectores no caso de uso: misturaria resolução, I/O e orquestração.

## Limites

Não há confirmação ou rejeição, criação de `Company`, transição para `PLANNING`,
execução/seleção de conector, planner, job, fila, worker, outbox, evidência,
claim, risco, relatório, endpoint ou frontend. A F4.3 não está autorizada e a
Fase 4 permanece em andamento.
