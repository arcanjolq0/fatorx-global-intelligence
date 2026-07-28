# ADR-0013 — Contexto do ator, autorização de serviços e auditoria coordenada

- Status: Accepted
- Data: 2026-07-28

## Contexto

A F2.4.1 materializou usuários internos, uma membership permanente por usuário/workspace e eventos mínimos append-only. Os repositórios são tenant-first, mas recebem IDs e não comprovam que o chamador pertence ao tenant. Também não havia política que interpretasse `OWNER`, `ADMIN`, `ANALYST` e `VIEWER`, proteção concorrente do último owner ou coordenação entre mutação e auditoria.

A F2.4.2 precisa aplicar essas regras sem antecipar autenticação, endpoints, sessões, tokens ou regras dentro da persistência. A Unit of Work é single-use e terminal depois de qualquer tentativa de finalização, portanto cada operação de serviço precisa abrir uma instância própria.

## Decisão

### Contexto confiável e escopo

`ActorContext` é imutável e contém somente `UserId`, `WorkspaceId` e `CorrelationId`. Ele representa um ator já autenticado por uma camada futura; não é credencial, token ou sessão. Nesta fase, testes e chamadas internas podem construí-lo. Quando existir uma API autenticada, somente sua fronteira de autenticação poderá criar o contexto confiável.

Serviços tenant-scoped não aceitam outro `workspace_id`. Toda autorização, consulta, criação e auditoria usa exclusivamente `actor.workspace_id`. IDs de recurso de outro tenant são consultados sob esse workspace e aparecem publicamente como ausentes.

### Política e autorização contextual

`Permission` é um catálogo fechado com create/read de Company e Investigation e add/change/deactivate/reactivate de Membership. `RolePermissionPolicy` é pura, determinística e sem IO:

| Papel | Company | Investigation | Membership |
|---|---|---|---|
| OWNER | create/read | create/read | todas as quatro operações; qualquer papel |
| ADMIN | create/read | create/read | quatro operações, somente sobre ANALYST/VIEWER |
| ANALYST | create/read | create/read | nenhuma |
| VIEWER | read | read | nenhuma |

`ContextualAuthorizer` usa a Unit of Work já aberta para exigir usuário existente/ativo, membership existente/ativa no workspace do contexto e permissão do papel. Ele retorna uma decisão pequena, nunca row, e não executa commit.

ADMIN não administra a própria membership e não cria, promove, rebaixa, desativa ou reativa OWNER/ADMIN. OWNER pode mudar a própria membership somente quando outro owner ativo permanece. Como ADMIN não pode autogerenciar e ANALYST/VIEWER não possuem permissões de membership, não existe autoelevação.

O bootstrap do primeiro owner não é resolvido por esse serviço. Ele dependerá de onboarding/administração futura; não existe caminho público para um usuário se tornar owner sem um owner já autorizado.

### Membership imutável e último owner

`WorkspaceMembership.change_role`, `deactivate` e `reactivate` retornam novos snapshots, preservam IDs/tenant/usuário e exigem timestamp UTC não regressivo. A entidade protege invariantes; o serviço decide autorização.

Antes de remover um owner ativo por rebaixamento ou desativação, o serviço chama `list_active_owners_for_update(workspace_id)`. O adaptador executa `SELECT ... FOR UPDATE`, filtra primeiro pelo workspace e ordena por ID. Todas as operações de retirada bloqueiam owners antes do alvo, mantendo uma ordem única. Sob `READ COMMITTED`, o segundo comando que aguardou reavalia as linhas depois do primeiro commit e enxerga o owner remanescente; se ele for o último, a operação é negada.

`get_for_update`, `list_active_owners_for_update` e `update` usam o guard original da F2.3.2. `update` corresponde simultaneamente a ID, workspace e usuário e altera apenas papel, estado e timestamps. O repositório não abre conexão, não finaliza transação e não conhece ator ou permissão.

### Auditoria coordenada

`AuditActionCode` e `AuditReasonCode` são catálogos fechados na aplicação. Eventos usam apenas IDs tipados, correlação e instante, sem payload arbitrário.

- Sucesso de mutação: mutação e `AuditEvent(SUCCESS)` são adicionados na mesma Unit of Work e recebem um único commit explícito. Rollback ou falha de commit remove ambos.
- Negação: nenhuma mutação é feita; `AuditEvent(DENIED)` é commitado e só então o erro público constante é levantado.
- Falha conhecida: validação e conflito usam `FAILURE` quando a transação ainda permite. Persistência abortada ou commit incerto nunca produz evento de sucesso independente e nunca reutiliza UoW envenenada.
- Leituras: sucesso não é auditado nesta fase para evitar volume e retenção prematuros; autorização negada ou ausência tenant-scoped gera evento de leitura negada sem ID de recurso de outro workspace.

A FK obrigatória de `audit_event.actor_user_id` torna impossível persistir `ACTOR_USER_NOT_FOUND`: uma identidade inexistente não pode ser referenciada. Nesse caso, a tentativa de auditoria falha, a transação é limpa e o erro original de autorização é preservado sem detalhe técnico. Alterar essa limitação exige nova decisão de schema; nenhuma migration é criada nesta tarefa.

## Consequências

- Workspace recebido de payload não pode substituir o escopo efetivo.
- A matriz é testável sem banco e as verificações contextuais ficam centralizadas.
- Repositórios continuam exclusivamente de persistência; regras de alvo e papel ficam no serviço.
- Duas retiradas concorrentes não conseguem remover todos os owners ativos.
- `Investigation.requested_by` é exatamente o usuário autorizado em novas criações, embora a coluna continue sem FK para preservar dados anteriores.
- Auditoria de sucesso é atômica, negações persistem sem mutação e falhas não são rotuladas como sucesso.
- Cada chamada usa uma Unit of Work nova; nenhuma conexão é aberta durante import ou construção da factory.
- Autenticação, API, bootstrap, transições de investigação, retenção/expurgo, conectores e integrações externas permanecem adiados.
