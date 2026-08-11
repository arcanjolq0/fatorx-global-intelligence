# F4.3.1 — Replay histórico durável da confirmação

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE.** Esta tarefa corrigiu a F4.3. Na data da
correção ela não autorizava a F4.4; essa autorização ocorreu posteriormente. A
Fase 4 segue aberta.

## Problema corrigido

A decisão F4.3 era reconstituída como se a Investigation atual ainda precisasse
ser o snapshot exato produzido pela confirmação. Depois de uma transição válida
posterior, inclusive cancelamento, a decisão deixava de ser carregável e o mesmo
`ConfirmEntityCandidate` não podia ser reproduzido.

## Contrato vigente

O validador único recebe explicitamente decisão, transição histórica,
Investigation atual, lote/candidato e Company.

O fato histórico deve registrar exatamente:

- `WAITING_FOR_ENTITY_CONFIRMATION -> PLANNING`;
- `version_after = version_before + 1`;
- mesmo workspace, Investigation, command, digest, decisão, Company, lote,
  candidato, políticas, revisor e timestamp.

O snapshot atual é uma condição separada. Deve manter a Company da decisão,
`active_candidate_batch_id = None`, versão maior ou igual à versão histórica e
um destes estados: `PLANNING`, `COLLECTING`, `NORMALIZING`, `VERIFYING`,
`ANALYZING`, `WAITING_FOR_REVIEW`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`
ou `CANCELLED`. Se a versão for exatamente a histórica, o estado deve ser
`PLANNING`. Estados anteriores, regressão de versão, troca de Company ou lote
ativo reintroduzido são rejeitados.

## Replay e classificação de falhas

Mesmo `command_id` e mesmo digest devolvem a decisão e a Company originais com
`replayed=True`. Esse caminho não lê relógio, gera IDs, materializa Company,
executa CAS, restaura `PLANNING` ou cria ledger, auditoria ou outro registro.

Transição e decisão são consultadas antes da classificação:

- ambas ausentes permitem um comando novo;
- par íntegro incompatível com o comando recebido é colisão;
- par íntegro compatível é validado e reproduzido;
- decisão sem transição ou transição F4.3 compatível sem decisão é corrupção;
- par internamente divergente é corrupção, mesmo que também conflite com a
  entrada recebida.

Corrupção falha fechada como `PersistenceDataError`, com mensagem pública
segura. Nenhum dado é reparado automaticamente.

## Persistência e escopo

As leituras por command, Investigation e ID carregam a transição histórica e o
contexto completo antes de devolver a decisão. O schema F4.3 já contém os
vínculos necessários: não há migration nova, alteração de migration, dependência
ou lockfile.

Permanecem fora do escopo: F4.4, rejeição, retorno à identificação, vínculo ou
merge de Company, planner, conectores, jobs, filas, workers, API, frontend,
evidências, claims, risco, relatórios e novas transições.

## Critérios de aceite

- replay imediato e depois de avanço/cancelamento preserva estado e versão;
- todas as leituras da decisão funcionam em estados posteriores compatíveis;
- matriz completa de estados e versões é validada;
- persistência parcial ou adulterada falha fechada e não vira colisão;
- concorrência, rollback, autorização, isolamento tenant-scoped,
  materialização e digests da F4.3 permanecem válidos;
- gates Python, PostgreSQL, Alembic, web, arquitetura e scanner passam;
- pacote de entrega reproduzível é gerado sem artefatos locais ou segredos.
