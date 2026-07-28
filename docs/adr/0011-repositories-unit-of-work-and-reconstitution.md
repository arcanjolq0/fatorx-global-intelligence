# ADR-0011 — Portas de persistência, Unit of Work e reconstituição de snapshots

- Status: Accepted
- Data: 2026-07-28

## Contexto

A F2.2 materializou `Workspace`, `Company` e `Investigation`, mas não definiu como a aplicação acessa esses registros nem como snapshots de investigação posteriores a `CREATED` retornam ao domínio. Usar o construtor de criação para leitura obrigaria a relaxar a invariante inicial; alterar atributos pelo adaptador criaria um contrato implícito e ignoraria validações. A fronteira de workspace também precisa ser preservada nas consultas sem transformar o repositório em serviço de autorização.

## Decisão

Definir portas pequenas em `application.ports`, usando `Protocol` e tipos do domínio, sem SQLAlchemy ou Alembic. Existem apenas `add` e `get` para os três agregados atuais. `CompanyRepository.get` e `InvestigationRepository.get` exigem `workspace_id` junto ao ID da entidade. `WorkspaceRepository.get` recebe somente `workspace_id`, pois o próprio agregado é a fronteira de tenant; não existe um workspace pai que possa compor seu filtro.

Implementar adaptadores PostgreSQL síncronos com SQLAlchemy Core. Cada repositório recebe uma conexão já aberta, usa `INSERT` e `SELECT` explícitos, não abre conexão, não executa commit e não devolve linhas SQLAlchemy. Conflitos de integridade e falhas esperadas são traduzidos para erros da aplicação com mensagens fixas; a causa técnica pode permanecer encadeada para observabilidade futura.

Usar uma Unit of Work síncrona, explícita e de uso único. Entrar no contexto abre uma conexão e uma transação e constrói os três repositórios sobre a mesma conexão. `commit()` é obrigatório para persistir; saída sem commit ou com exceção executa rollback. Commit duplicado, reuso da instância e operação após o encerramento falham com erro de estado da persistência. Transações aninhadas, retries, async e outbox não fazem parte desta decisão.

Manter o construtor público de `Investigation` restrito a `CREATED` com `state_version = 1`. O domínio oferece `Investigation.reconstitute(...)` exclusivamente para reconstruir snapshots persistidos. Esse contrato aceita estados canônicos, exige versão positiva, reaplica tipagem, normalização UTC, ordem temporal e coerência entre estado, `started_at` e `completed_at`. Ele não executa transição nem produz evento. O mapper chama esse contrato; não escreve atributos privados.

A factory de engine apenas valida `DATABASE_URL` e devolve um `Engine` pertencente ao chamador, sem singleton ou conexão no import. Nenhuma migration é necessária porque os adaptadores usam integralmente o schema da revisão `20260728_01`.

O filtro por workspace e as constraints compostas da F2.3 são defesa estrutural, não autorização contextual. Isolamento no nível dos serviços, `UserAccount`/`Membership` e auditoria mínima formam a F2.4. Eles não serão implementados como efeitos ocultos destes repositórios; qualquer porta, serviço, tabela ou migration adicional será decidida no escopo próprio da F2.4.

## Consequências

- Casos de uso futuros dependem de contratos da aplicação, não de SQLAlchemy.
- O domínio continua independente e valores inválidos do banco falham explicitamente durante o mapeamento.
- O limite transacional é verificável e uma operação parcial não é persistida sem commit.
- Consultas de empresa e investigação não recuperam registros de outro workspace, mas o chamador ainda precisará comprovar membership e permissão na F2.4.
- Adicionar listagens, atualização de estado, delete, autorização, auditoria ou novos agregados exige caso de uso e decisão separados.
