# F4.2 — Candidatos, matching e pausa para confirmação

Status: **ACEITA APÓS REVISÃO INDEPENDENTE, INCLUINDO A F4.2.1**
Data da implementação: 2026-07-29
Pré-condição: F4.1 **ACEITA APÓS REVISÃO INDEPENDENTE**

> Histórico da entrega inicial. A F4.2 foi corrigida pela F4.2.1 em 2026-08-01
> e foi posteriormente aceita após nova revisão independente. Consulte
> `F4_2_1_CORRECAO_INTEGRIDADE_RECONSTITUICAO.md`.

## Objetivo

Receber explicitamente um lote tipado de candidatos, avaliá-lo com política
determinística e versionada, persistir a explicação e pausar a investigação:

```text
IDENTIFYING
    -> avaliação e persistência de candidatos
WAITING_FOR_ENTITY_CONFIRMATION
```

Nenhum candidato é confirmado, rejeitado ou convertido em `Company`.

## Escopo materializado

- contratos imutáveis para lote, identidade, origem e política;
- máximo de 100 candidatos e chaves únicas por lote;
- snapshots canônicos fechados, schemas explícitos e SHA-256;
- matcher puro com sete dimensões, conflitos fortes e explicações;
- ordenação estável e independente da ordem de entrada;
- `RequestEntityConfirmation` como comando específico;
- autorização para owner, admin e analyst; viewer negado;
- digest da entrada obrigatório e compatível com a investigação;
- CAS tenant-scoped sem retry automático;
- replay durável sem matcher, relógio ou novos IDs;
- colisão de `command_id` com digest diferente;
- lote, candidato e dimensão append-only;
- ledger, auditoria, estado e lote em um único commit;
- migration reversível `20260729_04` sobre `20260729_03`;
- testes unitários, arquiteturais, PostgreSQL, concorrência e rollback.

## Política `ENTITY_MATCH_V1`

| Dimensão | Peso (bps) | Regra resumida |
|---|---:|---|
| identificador | 3500 | match exato; divergência comparável é conflito forte |
| nome | 2500 | legal/comercial exato, cruzado ou conjunto de tokens |
| domínio | 1200 | domínio normalizado exato ou divergente |
| geografia | 1000 | país exato; divergência é conflito forte |
| endereço | 800 | razão inteira de componentes comparáveis iguais |
| administradores | 700 | Jaccard inteiro entre conjuntos normalizados |
| temporal | 300 | data de constituição exata ou divergente |

Thresholds: `HIGH >= 8500`, `MEDIUM >= 6000`, senão `LOW`. Conflito forte
produz `EXCLUDED`, independentemente do total.

Texto é normalizado por NFKC, `casefold`, substituição de pontuação/símbolos por
espaço e colapso de whitespace. Não há transliteração. Todo cálculo usa inteiros;
não há float, IA, fuzzy library ou I/O.

O score total é a soma das contribuições dimensionais. Cobertura é a soma dos
pesos das dimensões comparáveis. Score mede compatibilidade segundo esta
política, não probabilidade, risco ou crédito. Uma dimensão ausente não pontua e
não representa confirmação.

Ranking: não excluído antes de excluído; classificação, score, cobertura e score
de identificador decrescentes; chave estável crescente como desempate final.

## Contratos e extensão da entrada

O `IdentificationInput` schema 1 permanece compatível. O schema 2 é opt-in e
adiciona administradores e data de constituição para comparabilidade das duas
dimensões correspondentes. Original e normalizado permanecem separados; resumo
e `repr` não revelam os valores.

`CandidateIdentitySnapshot` retém nomes, país, identificadores, domínio,
endereço, data e administradores. `CandidateOriginSnapshot` retém fonte,
conector/versão, referência opaca, instante e status de registro. Lote,
candidatos, política e avaliações têm serialização canônica e digest.

## Transação do caso de uso

1. validar comando, ator e permissão;
2. serializar por advisory lock do comando;
3. resolver replay ou colisão no ledger;
4. carregar investigação pelo workspace e validar versão/estado;
5. validar digest da entrada;
6. avaliar e ordenar candidatos sem I/O;
7. preparar registros imutáveis;
8. executar CAS da investigação;
9. gravar lote, candidatos, dimensões, ledger e auditoria;
10. fazer um único commit.

Falha em batch, ledger, auditoria ou commit reverte todas as mutações. Dois
comandos distintos concorrentes para a mesma versão deixam exatamente um lote.
Duas execuções do mesmo comando deixam um efeito e um replay durável.

## Persistência

Novas tabelas:

- `entity_candidate_batch`: escopo, política/snapshot, digests, comando e autor;
- `entity_candidate`: identidade/origem fechadas, rank, total, cobertura,
  classificação, conflito e decisão `PENDING_REVIEW`;
- `entity_candidate_dimension_score`: dimensão, score, peso, contribuição,
  disponibilidade, conflito e código explicativo.

`investigation.active_candidate_batch_id` vincula o único lote ativo.
`investigation_transition` e `audit_event` receberam os cinco metadados
allowlisted da F4.2. FKs compostas impedem vínculo cross-tenant. A constraint de
coerência do estado de espera é `NOT VALID` para preservar linha histórica, mas
é aplicada a toda linha nova.

## Segurança e privacidade

- candidatos são dados não confiáveis e passam por limites/validação fechada;
- `repr`, erros e auditoria expõem somente IDs e metadados allowlisted;
- snapshots, SQL e score completo não entram em logs/auditoria;
- não há segredos, rede, arquivo, ambiente ou subprocesso no matcher;
- não há claim factual, evidência admissível ou decisão automática.

## Exclusões

- confirmação/rejeição/edição de candidato;
- criação ou associação de empresa canônica;
- transição para `PLANNING` ou retomada;
- seleção ou execução de conector/simulador;
- planner, job, fila, worker, outbox, run ou endpoint;
- evidência, claim, risco, limite, relatório ou frontend novo;
- dependência, lockfile ou versão suportada nova.

## Critérios de aceitação comprovados

- política, normalização, conflitos, score, cobertura e ranking determinísticos;
- snapshots e política reconstruíveis após persistência;
- isolamento tenant-scoped e invariantes relacionais;
- replay/collision sem efeitos extras;
- concorrência real com `Barrier` e um vencedor;
- rollback integral após falhas injetadas;
- upgrade, downgrade e re-upgrade da migration;
- branches de conflito, replay e rollback cobertos;
- pacote `entity_resolution` acima de 95%;
- agregado conservador da aplicação/persistência F4.2 acima de 90%;
- gate global de 80% preservado.

Resultados e incidentes intermediários estão em
`docs/validation/f4.2-entity-candidate-review-foundation.md`.

## Limitações e pendências

- candidatos precisam ser fornecidos ao caso de uso; não há descoberta;
- a política V1 é intencionalmente conservadora e sem fuzzy/transliteração;
- ausência de dado reduz cobertura e pode manter classificação baixa;
- linha histórica de espera sem lote não é reconstituível sem saneamento;
- retenção e expurgo dos snapshots empresariais ainda exigem política;
- a F4.3 ainda não estava autorizada neste fechamento histórico;
- a Fase 4 não estava concluída e permanece em andamento.
