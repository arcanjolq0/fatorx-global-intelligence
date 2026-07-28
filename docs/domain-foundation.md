# Fundação do domínio — F2.1

## 1. Objetivo e limite

A tarefa F2.1 implementa somente tipos fundamentais, entidades imutáveis e invariantes de criação. O código está em `src/intelligence/domain` e depende exclusivamente da biblioteca padrão do Python.

Não fazem parte desta fundação: persistência, migrations, repositórios, serviços de aplicação, transições de estado, API de negócio, autenticação, conectores, evidências, scoring, relatórios ou integrações externas. Esses limites são verificados por teste arquitetural.

## 2. Decisões de representação

### 2.1 Identificadores

`WorkspaceId`, `UserId`, `CompanyId` e `InvestigationId` são tipos distintos, imutáveis e baseados em UUID não nulo. Eles podem ser criados com UUID v4 ou reconstruídos a partir de um objeto `UUID` ou de sua representação textual canônica.

A separação de classes impede que identificadores de agregados diferentes sejam iguais por acidente, mesmo quando encapsulam os mesmos bytes. A escolha reutiliza a biblioteca padrão e não cria uma dependência de framework de validação.

### 2.2 País e moeda

`CountryCode` aceita exatamente duas letras ASCII e normaliza para maiúsculas. `CurrencyCode` aceita exatamente três letras ASCII e também normaliza para maiúsculas.

Nesta etapa, a validação é deliberadamente de formato, não de pertinência às listas oficiais ISO 3166-1 e ISO 4217. Assim, valores com formato válido, como `ZZ` ou `XYZ`, são aceitos. A validação contra catálogos oficiais exigirá uma fonte versionada e política de atualização, que devem ser definidas em tarefa posterior.

`JurisdictionCode` não foi criado. A F2.1 não possui ainda uma regra concreta que diferencie jurisdição registral de país; introduzir o tipo agora criaria uma abstração sem comportamento definido. A distinção permanece obrigatória antes de modelar registros subnacionais ou múltiplos registros por país.

### 2.3 Valores monetários

`Money` contém um `Decimal` finito e um `CurrencyCode` explícito. `float`, NaN, infinito e moeda não tipada são rejeitados. Soma e subtração somente aceitam valores na mesma moeda e calculam com contexto suficiente para preservar a precisão dos operandos.

Não há conversão cambial, quantização, escala monetária implícita, arredondamento ou formatação. Uma conversão futura deverá ser um dado derivado separado, com taxa, instante, fonte e método rastreáveis.

### 2.4 Instantes

Todo instante de domínio deve ser um `datetime` com fuso. O construtor das entidades normaliza o valor para UTC; instantes ingênuos são rejeitados. Datas civis de incorporação e dissolução usam `date`, pois não representam instantes.

## 3. Entidades e invariantes

As entidades são `dataclass` imutáveis, com `slots` e parâmetros nomeados. Elas representam snapshots validados, não objetos ligados a ORM.

### 3.1 Workspace

`Workspace` é a fronteira explícita de tenancy. Suas invariantes são:

- identificador e status precisam usar os tipos de domínio correspondentes;
- nome e versão da política de retenção não podem ser vazios;
- textos periféricos são normalizados com remoção de espaços nas extremidades;
- `created_at` e `updated_at` são instantes UTC;
- `updated_at` não pode anteceder `created_at`.

Os estados iniciais disponíveis são `ACTIVE`, `SUSPENDED` e `ARCHIVED`. A semântica de autorização e as transições entre eles não pertencem à F2.1.

### 3.2 Company

Toda `Company` contém um `workspace_id`; não existe empresa global fora da fronteira de tenant nesta representação. Suas invariantes são:

- identificadores, país e status precisam ser tipados;
- razão social é obrigatória; nome comercial e forma jurídica, quando presentes, não podem ser vazios;
- datas de incorporação e dissolução são datas civis, não `datetime`;
- dissolução não pode anteceder incorporação;
- status `DISSOLVED` exige `dissolved_on`, e outros estados proíbem essa data;
- `official_domain`, quando presente, contém somente um host normalizado, sem protocolo, porta, caminho, query, fragmento ou credenciais;
- `updated_at` não pode anteceder `created_at`.

Os estados disponíveis são `ACTIVE`, `INACTIVE` e `DISSOLVED`. Aliases, identificadores registrais, endereços, relações societárias e histórico de alterações continuam no modelo planejado, mas não foram antecipados nesta tarefa.

### 3.3 Investigation

Uma nova `Investigation` sempre nasce em `CREATED`, com `state_version = 1`. A versão inicial é uma decisão local da representação e prepara o controle otimista previsto no ciclo de vida; a evolução transacional será definida com a persistência.

Suas invariantes são:

- investigação, workspace, solicitante e empresa confirmada usam IDs distintos e tipados;
- perfil é obrigatório e país usa `CountryCode`;
- orçamento, quando presente, usa `Money`;
- todos os instantes são normalizados para UTC;
- início não pode anteceder criação;
- uma investigação em `CREATED` não pode possuir `started_at`;
- deadline, quando presente, não pode anteceder criação;
- conclusão exige início e não pode antecedê-lo;
- um snapshot novo não pode declarar estado diferente de `CREATED`, versão diferente de `1` nem `completed_at`.

O enum implementa exatamente os estados de `docs/investigation-lifecycle.md`. Os estados terminais são `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED` e `CANCELLED`. A lista de transições permitidas, condições, comandos e atualização atômica de `state_version` não foi implementada.

## 4. Erros

Falhas de validação usam exceções de domínio sob `DomainError`. Existem erros específicos para identificadores, país, moeda, dinheiro e instantes, além de `InvariantViolationError` para inconsistências entre campos de uma entidade. As mensagens descrevem a regra violada e não incluem conteúdo sensível.

## 5. Dependências e ADRs

Nenhuma dependência foi adicionada. `dataclasses`, `datetime`, `decimal`, `enum`, `re` e `uuid` pertencem à biblioteca padrão.

Não foi necessário criar ADR. As escolhas implementam as fronteiras já aceitas no ADR-0002, a separação por workspace do ADR-0008 e as representações já definidas em `docs/data-model.md`. Imutabilidade e `dataclass` são decisões locais e reversíveis nesta etapa; uma futura alteração de representação que afete persistência ou contratos públicos deverá ser registrada conforme a convenção dos ADRs.

## 6. Itens adiados

Permanecem para tarefas posteriores, sem implementação implícita:

- catálogos oficiais e versionados de países e moedas;
- definição de `JurisdictionCode` e registros subnacionais;
- usuários, memberships e regras de autorização;
- aliases, endereços, identificadores externos e relações de empresas;
- transições da investigação e comandos de domínio;
- repositórios, Unit of Work, round-trip de entidades e políticas de consulta por workspace;
- auditoria persistida e concorrência otimista;
- contratos de conectores, evidências, risco e relatórios.

## 7. Decisões pré-schema da F2.2

Estas decisões alinham o domínio e o primeiro schema PostgreSQL. A motivação arquitetural e as consequências estão no ADR-0010.

### 7.1 `started_at`

Uma investigação em `CREATED` não pode possuir `started_at`. O instante representa o início operacional e será atribuído pela futura transição `CREATED -> IDENTIFYING`. A F2.2 somente aplica a invariante; não implementa a transição.

### 7.2 Empresa confirmada na criação

`confirmed_company_id` pode ser informado em `CREATED` quando a pesquisa parte de uma empresa canônica já cadastrada no mesmo workspace. A referência não autoriza pular silenciosamente etapas do ciclo de vida: a F2.3 deverá definir se a identificação apenas valida essa empresa ou ainda produz candidatos. A foreign key composta do schema impede referência entre workspaces.

### 7.3 Deadline

`deadline_at`, quando presente, deve ser igual ou posterior a `created_at`. Aceitar deadline já expirado na criação tornaria budget, retry e término inconsistentes. A regra será aplicada no construtor do domínio e em constraint SQL.

### 7.4 Jurisdição

`JurisdictionCode` continua adiado e a migration inicial não terá `jurisdiction_code`. País não será usado silenciosamente como sinônimo de jurisdição. O tipo e a coluna somente serão introduzidos juntos, após contrato para registros nacionais, subnacionais e múltiplos registros por país.

### 7.5 Domínio corporativo

`official_domain` recebe validação também no PostgreSQL, além da validação no domínio. A constraint aceita somente o formato canônico já persistível — minúsculas, labels DNS sem hífen nas extremidades e até 253 caracteres — e rejeita protocolo, porta, caminho e credenciais. Ela não comprova propriedade, atividade ou unicidade do domínio; essas conclusões continuam dependentes de política e evidência.

### 7.6 Coerência persistida de estado e timestamps

O hardening F2.2.1 define `started_at` como o instante em que a execução do ciclo deixa `CREATED` e `completed_at` como o instante em que entra em qualquer estado terminal. Normalmente, o início é atribuído em `CREATED -> IDENTIFYING`. Portanto, `CREATED` exige início nulo, qualquer outro estado exige início preenchido, estados terminais exigem término preenchido e estados não terminais proíbem término.

Para `FAILED` e `CANCELLED`, `completed_at` significa terminalização, não sucesso. No cancelamento direto antes da identificação, `started_at` e `completed_at` recebem o mesmo instante: o ciclo inicia apenas para registrar sua terminalização atômica. A regra é aplicada no schema para proteger futuros snapshots reconstruídos e escritas diretas. O construtor de domínio existente continua limitado ao snapshot inicial em `CREATED`; nenhum método de transição ou reconstrução foi introduzido na F2.2.1.
