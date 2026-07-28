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

## Adendo F2.3.1 — vínculo à transação original

Data: 2026-07-28.

A implementação inicial entregava somente a `Connection` aos repositórios e verificava `connection.closed`. Depois de `commit()` ou `rollback()`, a conexão permanecia aberta até a saída do contexto; uma referência de repositório já capturada poderia executar outra instrução e acionar o autobegin do SQLAlchemy fora da transação controlada pela Unit of Work.

Os três repositórios passam a compartilhar um guard criado pela Unit of Work com a `Connection` e a `RootTransaction` originais. Antes de qualquer `INSERT` ou `SELECT`, o guard exige simultaneamente:

- conexão não fechada;
- `RootTransaction.is_active` verdadeiro;
- `connection.get_transaction()` idêntica à `RootTransaction` original.

`connection.in_transaction()` isoladamente não é suficiente porque não comprova identidade. Se qualquer condição falhar, a operação termina em `PersistenceStateError` antes de chamar `execute`, impedindo autobegin. A Unit of Work usa o mesmo guard para commit e rollback, continua sendo a única responsável pelo commit e define erros explícitos para chamadas duplicadas.

Falhas SQLAlchemy de início, commit e rollback são traduzidas para `PersistenceError` com mensagens fixas; a causa técnica permanece encadeada sem integrar a mensagem pública. Nenhuma migration, dependência, transação aninhada, retry ou funcionalidade da F2.4 é introduzida.

## Adendo F2.3.2 — invalidação terminal antes da finalização

Data: 2026-07-28.

O estado observado de uma `RootTransaction` não comprova que uma tentativa de finalização anterior teve resultado conhecido. Um erro em `commit()` ou `rollback()` pode deixar `is_active` verdadeiro e preservar a identidade retornada por `connection.get_transaction()`. Reutilizar a fronteira nessa situação permitiria novas operações sobre uma transação cujo resultado é incerto.

O guard passa a possuir estado explícito e irreversível de invalidação. A Unit of Work o invalida e registra que a finalização foi tentada antes de delegar ao SQLAlchemy. A partir desse instante:

- nenhum repositório pode ler ou escrever;
- commit e rollback públicos não podem ser tentados novamente;
- o resultado da chamada do driver não revalida o guard;
- somente o `__exit__` pode acessar diretamente a transação e a conexão para tentar rollback e close técnicos.

Falha ao iniciar marca a instância como terminal antes da tentativa de fechar uma conexão parcialmente aberta. O `__exit__` também marca a instância e invalida o guard antes da limpeza; eventual falha de close é traduzida sem fazer `is_closed` voltar a falso. Quando uma exceção do corpo já está em propagação, falhas secundárias de limpeza não a substituem.

Portas de aplicação e contratos de repositório permanecem inalterados. Nenhuma migration, dependência, retry, reconciliação transacional ou funcionalidade da F2.4 é introduzida.
