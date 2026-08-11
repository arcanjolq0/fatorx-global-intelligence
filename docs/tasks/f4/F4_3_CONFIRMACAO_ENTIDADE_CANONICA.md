# F4.3 — Confirmação de entidade canônica

## Estado

**ACEITA APÓS REVISÃO INDEPENDENTE, INCLUINDO A CORREÇÃO F4.3.1.** A entrega
original permanece registrada abaixo. A Fase 4 continua em andamento.

## Escopo entregue

- comando humano imutável `ConfirmEntityCandidate`;
- permissão específica para OWNER, ADMIN e ANALYST;
- motivos fechados e regras de override;
- bloqueio absoluto de candidato `EXCLUDED`;
- política determinística e versionada `COMPANY_MATERIALIZATION_V1`;
- criação de uma nova `Company`, nunca vínculo automático com existente;
- decisão append-only com linhagem e digests;
- transição atômica `WAITING_FOR_ENTITY_CONFIRMATION -> PLANNING`;
- CAS, lock de comando, replay durável e colisão tipada;
- migration `20260801_05`, constraints tenant-scoped e downgrade fail-safe que
  recusa decisões F4.3 ou Company UNKNOWN incompatíveis.

## Invariantes

O lote informado deve ser o lote ativo e o candidato deve existir nele. LOW e
rank maior que 1 exigem `MANUAL_OVERRIDE`; rank 1 HIGH/MEDIUM admite motivo não
override. O comando não aceita candidato inline, Company ID, destino ou texto
livre.

O mapeamento V1 usa nome legal original, trade name original, país, data de
constituição e domínio normalizado. `legal_form` e `dissolved_on` são nulos.
ACTIVE vira ACTIVE, INACTIVE vira INACTIVE e DISSOLVED/UNKNOWN/ausente vira
UNKNOWN.

Após a decisão, a Investigation tem Company, não tem lote ativo e avança uma
única versão. Entrada, `started_at`, orçamento, deadline, solicitante, perfil e
país são preservados.

## Limitações deliberadas

Duas investigações distintas podem, nesta fase, criar duas Companies para a
mesma entidade real. Reconciliação, vínculo com Company existente, rejeição,
nova identificação, planner, conectores, evidence, claims, risk e reporting não
pertencem à F4.3. Candidato e decisão não são evidência.

## Histórico de correção F4.3.1

A implementação original validava a decisão contra o snapshot imediatamente
posterior à confirmação. Isso impedia carregar ou reproduzir uma confirmação
íntegra quando a investigação avançava além de `PLANNING` ou era cancelada.

A F4.3.1 separa o fato histórico da confirmação — transição exata, incremento
unitário e todos os vínculos/digests — do estado atual. O snapshot atual aceita
somente estados pós-confirmação, exige a mesma Company, lote ativo nulo e versão
maior ou igual à histórica; igualdade de versão exige `PLANNING`. O replay não
restaura estado nem produz qualquer efeito. A especificação completa está em
`F4_3_1_REPLAY_HISTORICO_CONFIRMACAO.md`.
