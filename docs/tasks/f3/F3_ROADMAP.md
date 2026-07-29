# Fase 3 — Framework de conectores simulados

## Estado de execução

- F3.1 concluída em 2026-07-28;
- F3.2 concluída em 2026-07-29;
- F3.3 **IMPLEMENTADA — AGUARDANDO REVISÃO INDEPENDENTE** em 2026-07-29;
- gate G3 permanece não aceito até revisão independente; Fase 4 não autorizada.

## 1. Objetivo

Construir uma fronteira tipada, segura e testável entre o núcleo da aplicação e
futuras fontes externas, sem consultar qualquer fonte real e sem permitir que
formatos de fornecedores contaminem domínio, persistência, scoring, evidências,
relatórios ou resolução de entidades.

A Fase 3 comprova o gate G3 do `PLANS.md`:

> qualquer conector simulado que viole o contrato falha nos testes; nenhum
> conector escreve no domínio ou faz acesso externo.

## 2. Resultado esperado ao final da fase

Ao concluir F3.1, F3.2 e F3.3, o projeto deverá possuir:

- contratos imutáveis e versionados;
- descritores de conectores;
- vocabulário explícito de capacidades, operações, acesso e falhas;
- queries, candidatos, observações, artefatos e outcomes tipados;
- registro de conectores sem importação dinâmica;
- conectores simulados determinísticos;
- suíte reutilizável de testes de contrato;
- execução de uma única operação com deadline, cancelamento, retry limitado,
  budget e idempotência;
- nenhuma chamada de internet;
- nenhuma dependência de fornecedor;
- nenhuma escrita em tabelas do domínio;
- nenhuma alteração do estado da investigação;
- nenhuma criação de evidência ou claim canônico.

## 3. Fronteiras arquiteturais

### `domain`

Permanece independente. Não importa conectores, aplicação, infraestrutura,
HTTP, asyncio de integração ou contratos externos.

### `application`

Pode consumir portas de execução futuramente, mas a Fase 3 não cria ainda o
planejador de investigação, jobs ou transições.

### `connectors`

Contém:

- contratos de integração;
- descritores;
- tipos neutros;
- registro;
- conectores simulados;
- controles de execução de uma operação.

Pode importar tipos fortes estáveis do domínio, como IDs, país, moeda e dinheiro.
Não pode importar persistência PostgreSQL, repositórios, serviços de autorização,
scoring, evidências, claims ou relatórios.

### `orchestration`

Permanece fora da Fase 3. Será iniciada na Fase 4.

## 4. Decisões gerais recomendadas

### 4.1 Contrato sem framework

Usar `dataclasses`, `enum`, `typing.Protocol`, `Decimal`, `datetime`, `UUID`,
`hashlib` e demais recursos da biblioteca padrão.

Pydantic continua reservado às bordas de API. Nenhuma dependência é necessária
para os contratos ou simuladores.

### 4.2 Cobertura global explícita

Conjunto vazio de países nunca deve significar “global”.

O descritor deve representar explicitamente:

- cobertura global; ou
- conjunto não vazio de países ISO alfa-2.

Essa decisão evita ativar uma fonte mundial por omissão de configuração.

### 4.3 Dados neutros, não fatos

O conector produz `CandidateObservation` e `Observation`.

Ele não:

- confirma identidade;
- cria `Company`;
- cria evidência canônica;
- cria claim;
- decide risco;
- redige relatório.

### 4.4 Sem dados arbitrários

Evitar `Any`, payloads JSON genéricos e dicionários livres no contrato central.

Quando dados brutos forem necessários, eles entram como artefato delimitado,
digest e metadados mínimos, nunca como objeto executável ou instrução.

### 4.5 Credenciais fora dos envelopes

O contrato pode transportar uma referência opaca ou handle não serializável,
mas nunca token, senha, cookie ou chave.

Nenhum segredo deve aparecer em:

- `repr`;
- igualdade;
- erro;
- warning;
- fixture;
- snapshot;
- digest textual de teste.

### 4.6 Versionamento

Existem versões distintas:

- versão do conector;
- versão do contrato;
- versão de schema de observação;
- versão da política de fonte.

Mudança incompatível do envelope incrementa major. O registro rejeita major
desconhecida.

## 5. Decomposição

# F3.1 — Contratos tipados e registro

## Objetivo

Implementar somente os tipos, invariantes, Protocol assíncrono e registro de
conectores.

## Entregas

- tipos fortes de integração;
- `SemanticVersion`;
- `ConnectorDescriptor`;
- cobertura global ou por países;
- capacidades, operações e acesso;
- `ConnectorContext`;
- `CompanyQuery`;
- identificadores de candidato;
- observações neutras;
- artefatos e referências;
- source snapshot, paginação, uso, warnings e erros;
- `ConnectorOutcome[T]`;
- `Connector` Protocol;
- `ConnectorRegistry`;
- validação de compatibilidade;
- testes unitários e arquiteturais;
- ADR e documentação.

## Exclusões

- simuladores;
- retry;
- execução com timeout;
- cache/idempotency store;
- HTTP;
- rede;
- sleep real;
- persistência;
- orquestração;
- estado de investigação.

## Commit sugerido

`feat: define connector contracts and registry`

# F3.2 — Simuladores determinísticos e suíte de contrato

Status: **concluída em 2026-07-29**.

## Objetivo

Provar que o contrato consegue representar comportamentos normais e falhas, e
criar uma suíte reutilizável que qualquer futuro conector deverá passar.

## Entregas implementadas

- connector simulado de registro empresarial;
- fixtures exclusivamente sintéticas;
- cenários determinísticos:
  - sucesso;
  - nenhum resultado;
  - múltiplos candidatos;
  - parcial;
  - rate limit;
  - timeout tipado;
  - indisponibilidade;
  - resposta inválida;
  - cancelamento;
  - policy blocked;
  - budget exceeded;
- suíte parametrizável de contrato;
- conectores deliberadamente inválidos apenas nos testes para provar que a suíte
  detecta violações;
- ausência total de rede e relógio real.

## Exclusões

- retries automáticos;
- executor genérico;
- paralelismo;
- banco;
- filas;
- evidências;
- orquestração.

## Commit sugerido

`test: add deterministic connector simulators and contract suite`

# F3.3 — Controles de execução de uma operação

Status: **IMPLEMENTADA — AGUARDANDO REVISÃO INDEPENDENTE**.

## Objetivo

Executar uma única operação de um conector sob políticas previsíveis, sem criar
planejador, jobs ou máquina de estados.

## Entregas previstas

- runner de operação única;
- validação de suporte antes de I/O;
- deadline monotônico;
- cancelamento cooperativo;
- retry limitado somente para códigos permitidos;
- backoff e jitter injetáveis/determinísticos;
- budget precheck e accounting;
- idempotência por `operation_id` e fingerprint da requisição;
- proteção contra reutilização do mesmo ID com conteúdo diferente;
- limite de paginação e itens;
- digest;
- observabilidade estrutural sem payload;
- portas pequenas para relógio, sleeper e idempotência;
- adapters somente em memória para testes;
- testes de corrida, timeout, retry e replay.

## Exclusões

- execução paralela;
- scheduler;
- worker;
- fila;
- alteração de Investigation;
- consolidação entre conectores;
- resolução de entidades;
- evidências.

## Commit sugerido

`feat: enforce connector execution controls`

## 6. Gate G3

A Fase 3 só termina quando:

1. o contrato é versionado e imutável;
2. descritores inválidos são rejeitados;
3. país/capacidade/operação não suportados falham antes de I/O;
4. `NO_RESULTS` não é falha;
5. outcomes inconsistentes são impossíveis;
6. simuladores são determinísticos;
7. uma suíte comum detecta conectores incompatíveis;
8. deadline e cancelamento são comprovados;
9. retries são permitidos somente por política;
10. budget é obrigatório quando configurado;
11. replay idempotente não cria efeito duplicado;
12. colisão de `operation_id` é rejeitada;
13. nenhum teste acessa rede;
14. nenhum conector importa persistência, scoring, evidência ou relatório;
15. nenhum conector escreve no domínio;
16. nenhuma fase posterior foi antecipada.

## 7. Riscos a observar

- criar um “mega-envelope” com muitos `dict[str, Any]`;
- misturar candidato com empresa canônica;
- armazenar cursor secreto em logs ou persistência;
- tratar conjunto vazio de países como global;
- retry em erro não retriável;
- usar timeout de parede sem monotonic clock;
- permitir budget em moeda incompatível;
- gerar digest com segredo;
- usar singleton global de registro;
- importar conectores por descoberta automática insegura;
- antecipar HTTP e SSRF sem fonte aprovada;
- criar orquestrador disfarçado de runner.

## 8. Próxima fase

Somente depois do gate G3, a Fase 4 poderá:

- criar jobs;
- planejar por país/capacidade;
- executar conectores em paralelo;
- persistir lifecycle;
- gerar candidatos;
- aplicar política de resolução;
- pausar para revisão humana.

Nada disso pertence à Fase 3. A implementação da F3.3 não constitui aceite do
gate G3 nem autorização para iniciar qualquer item desta seção.
