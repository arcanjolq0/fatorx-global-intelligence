# ADR-0012 — Identidades internas, memberships e auditoria mínima

- Status: Accepted
- Data: 2026-07-28

## Contexto

A F2.4.1 precisa materializar identidade interna, vínculo de usuário com workspace e eventos mínimos de auditoria sem antecipar autenticação ou autorização. O modelo alvo anterior citava sujeito externo de autenticação e outro vocabulário de papéis, mas não havia contrato aprovado para provedor, credencial ou matriz de permissões. A tabela `investigation` já contém `requested_by` sem foreign key e bancos atualizados podem possuir UUIDs sem usuário correspondente.

## Decisão

### Identidade interna e e-mail

`UserAccount` representa somente uma identidade interna. Não contém senha, hash, credencial, sessão, token, login, sujeito OAuth, MFA ou recuperação de conta. A integração com um provedor de autenticação exige decisão e tarefa próprias.

`EmailAddress` usa uma forma canônica deliberadamente simples: rejeita caracteres de controle, remove somente whitespace externo, rejeita whitespace interno, converte toda a representação para minúsculas, limita o total a 254 caracteres e exige exatamente um `@`, com parte local e domínio não vazios. Essa regra não consulta DNS e não promete validar todos os formatos permitidos pelos RFCs de e-mail.

O PostgreSQL armazena somente a forma canônica, repete as verificações mínimas por `CHECK` e aplica `UNIQUE(email)`. Não será instalada a extensão `citext`: a normalização no domínio e a constraint de lowercase tornam a comparação comum suficiente nesta fase.

### Membership por workspace

`WorkspaceMembership` possui identidade própria e a combinação `(workspace_id, user_id)` é permanentemente única. Existe no máximo uma linha por usuário e workspace. Uma futura desativação ou reativação deverá alterar controladamente esse snapshot, em vez de criar linhas concorrentes; esses comandos, a proteção do último owner e a matriz de permissões pertencem à F2.4.2.

Os papéis persistidos iniciais são `OWNER`, `ADMIN`, `ANALYST` e `VIEWER`. Esta decisão substitui, para a membership materializada, o vocabulário apenas planejado no ADR-0008. Ela ainda não atribui permissões aos papéis.

### `Investigation.requested_by`

A nova migration não adiciona foreign key em `investigation.requested_by`. Não existe backfill confiável para UUIDs já persistidos, e inventar usuário, e-mail ou identificador violaria a integridade do projeto. A coluna continua sendo uma referência tipada, mas não comprova existência, membership ou autorização.

A F2.4.2 deverá validar o ator e sua membership nos serviços para novas operações. Uma foreign key futura somente poderá ser criada após reconciliação explícita dos dados existentes e teste de upgrade com órfãos; a F2.4.1 não altera identificadores nem descarta investigações.

### Auditoria append-only e retenção

`AuditEvent` é um snapshot imutável. Sua porta e seu adaptador oferecem apenas `add`; não existem update, delete, save ou replace. Correções futuras produzem novo evento. Append-only, nesta etapa, é uma garantia do domínio e da superfície de persistência, não uma proteção contra SQL administrativo: nenhuma trigger será criada sem decisão e necessidade operacional próprias.

O evento contém somente IDs tipados, código de ação, tipo e ID opcional do recurso, resultado, motivo opcional, correlação e instante. Não existe coluna JSON ou payload arbitrário. Senhas, tokens, credenciais, documentos, páginas, SQL, URL de banco e dados pessoais desnecessários são proibidos.

Eventos devem sobreviver à desativação de usuário ou workspace. As foreign keys para ambos usam `RESTRICT`, sem cascata destrutiva. Não há expurgo nesta fase; os eventos permanecem até existir política de retenção aprovada. Eventual expurgo ou anonimização deverá ser controlado, preservar o mínimo legalmente permitido e gerar trilha auditável.

## Consequências

- Identidade pode ser persistida sem criar mecanismo de autenticação.
- E-mail duplicado é rejeitado deterministicamente sem extensão PostgreSQL.
- Membership não acumula linhas históricas duplicadas; mudanças futuras exigirão comandos e auditoria da F2.4.2.
- Investigações existentes atualizam com segurança, mas `requested_by` ainda exige validação no serviço futuro.
- Auditoria é append-only pela API de domínio/persistência, com retenção conservadora e sem cascata.
- A Unit of Work passa a expor três novos repositórios sobre o mesmo guard da F2.3.2.
- Contexto do ator, autorização, permissões, serviços de membership, proteção do último owner e auditoria automática continuam fora do escopo.
