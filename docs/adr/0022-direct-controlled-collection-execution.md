# ADR 0022 — Execução direta controlada e recibo operacional redigido

- Status: Accepted
- Data: 2026-08-11
- Decisores: responsáveis técnicos do Fator X Global Intelligence
- Depende de: ADR 0015 e ADR 0021

## Contexto

A F4.5/F4.5.1 congela um manifesto, mas não o executa. O primeiro corte de
execução precisa provar o vínculo entre uma operação persistida e o runner F3.3
sem antecipar topologia distribuída, fontes reais ou a cadeia de evidências.
Também precisa impedir que o retorno sintético seja confundido com fato
admissível.

## Decisão

Executar uma única operação `SEARCH` por comando. O conector é fornecido
explicitamente pela composição da aplicação, deve constar de allowlist, suportar
`TEST` e coincidir integralmente com o descritor congelado no manifesto. Não há
registry lookup, seleção dinâmica ou fallback.

Persistir um registro de ownership tenant-scoped antes de chamar o runner. O ownership inclui
comando/digest, run/operação, ator, descritor, source policy, locales, snapshot e
digest da política de execução e instante. A unicidade por
`(workspace_id, collection_operation_id)` garante uma única propriedade
durável. Após o runner, persistir em nova transação somente a conclusão redigida:
status, códigos fechados, accounting, fingerprints/digests, idempotência e
controle. Itens e payloads são descartados nessa fronteira.

O termo `ownership` é deliberadamente distinto de `Claim`: ele representa
propriedade operacional para impedir I/O duplicado, enquanto `Claim` permanece
reservado à afirmação factual estruturada do contrato de evidências.

Na correção F4.6.1, a aplicação persiste exclusivamente o descritor do preflight
validado antes do commit. O runner refaz seu preflight depois do commit e exige
igualdade exata com esse descritor antes de reservar idempotência ou chamar a
operação. Mudança temporal do descritor falha fechada sem I/O.

Na F4.6.2, uma divergência detectada depois de uma tentativa é uma falha terminal
de continuidade de identidade. Ela pode produzir somente a conclusão redigida
da tentativa já iniciada; não participa da política de retry, ainda que
`INVALID_RESPONSE` esteja explicitamente configurado como retriável.

O serviço revalida manifesto, prazo civil, budget e dependências. A query vem da
Company persistida. Replay de conclusão íntegra não lê clock nem chama conector.
Ownership sem conclusão é estado em andamento e não autoriza nova chamada. O
manifesto permanece imutável em `PENDING`; nenhuma transição de Investigation é
executada.

## Consequências

- o I/O nunca ocorre antes de ownership durável;
- a história permite auditar qual contrato foi tentado sem armazenar conteúdo
  empresarial retornado;
- falha entre ownership e conclusão deixa ownership órfão intencionalmente fail-closed;
- dependências podem usar somente outcomes estruturais utilizáveis;
- ownership e resultado não são evidência, claim factual, risco ou relatório;
- recovery, leases, jobs, paralelismo e fechamento da coleta ficam adiados.

## Alternativas rejeitadas

- atualizar `CollectionOperation` para `RUNNING/SUCCEEDED`: misturaria manifesto
  imutável com lifecycle ainda não projetado;
- persistir o envelope integral: anteciparia retenção, admissibilidade e cadeia
  de custódia da Fase 5;
- chamar o conector antes do commit: permitiria efeito sem ownership durável;
- usar outbox/worker/fila: ampliaria a F4.6 para topologia operacional;
- aceitar conector indicado no comando: permitiria desvio do manifesto;
- executar fonte real: violaria o gate G6 e as aprovações por fonte.
