# ADR-0014 — Contratos de conectores e registro explícito

- Status: Accepted
- Data: 2026-07-28

## Contexto

A Fase 2 concluiu domínio, persistência inicial, identidades internas e serviços
tenant-scoped. A F3.1 precisa criar a fronteira puramente tipada de futuras
integrações sem antecipar fonte, simulador, executor, rede, persistência ou
orquestração. O ADR-0002 já impede conectores de confirmar entidades ou criar
evidências, claims, risco e relatórios, mas ainda não fixa localização,
versionamento, cobertura e registro do contrato executável.

## Decisão

### Localização e dependências

Os contratos ficam em `src/intelligence/connectors/`. A camada pode importar
somente biblioteca padrão e tipos estáveis do domínio necessários ao envelope:
IDs de workspace/investigação/correlação, país, moeda, dinheiro e normalização
UTC. O domínio não importa connectors. Connectors não importa aplicação,
persistência PostgreSQL, repositórios, infraestrutura, evidências, claims,
risk, reporting ou frameworks web.

### Versionamento

A versão inicial do contrato é `1.0.0`. `SemanticVersion` aceita somente a forma
canônica `MAJOR.MINOR.PATCH`, com componentes inteiros não negativos e sem
zeros à esquerda, sinais, espaços, prerelease ou build metadata. Comparação e
hashing usam a tupla `(major, minor, patch)`. Compatibilidade é explícita e
restrita ao mesmo major; o registro conhece somente o major 1 nesta tarefa.

Versão do conector, versão do contrato, versão do schema de observação e versão
da política de fonte permanecem conceitos distintos.

### Cobertura explícita

`CoverageKind` possui somente `GLOBAL` e `COUNTRY_SET`. Cobertura global exige
conjunto de países vazio. Cobertura por países exige `frozenset[CountryCode]`
não vazio. Qualquer estado contraditório é inválido, e conjunto vazio nunca
ativa cobertura global por omissão.

### Neutralidade e segurança dos envelopes

Capacidades, operações, acesso, modo, status, falhas, retenção e warnings usam
vocabulários fechados. `CandidateObservation` e `Observation` transportam
somente valores escalares restritos; não aceitam `Any`, JSON genérico ou
dicionário livre. Candidato não é `Company`, observação não é claim e locator
de artefato não é evidência canônica.

O descritor contém apenas o nome de uma referência de credencial. O contexto
pode receber um handle opaco definido por `Protocol`, excluído de `repr`,
igualdade e hash. Nenhum envelope contém token, senha, cookie ou chave.

Deadline é um valor monotônico absoluto tipado, e cancelamento é uma porta
cooperativa somente de leitura. F3.1 não consulta relógio, espera, cancela nem
aplica timeout. Artefato inline tem limite pequeno, bytes ocultos no `repr`,
tamanho e SHA-256 calculados; referência é opaca, sem URL ou método de busca.

### Protocol e registro

`Connector` é um `Protocol` assíncrono sem classe-base obrigatória. A assinatura
de `fetch_document` permanece uniforme; um descritor que não declara
`FETCH_DOCUMENT` nunca é selecionado para essa operação, portanto a rejeição
ocorre antes de qualquer chamada.

`ConnectorRegistry` é instanciável e explícito. Não existe singleton,
descoberta dinâmica, `importlib`, entry point, leitura de filesystem,
configuração externa ou registro automático no import. O registro valida o
descritor e a compatibilidade de major, rejeita duplicidade e seleciona em
ordem estável de `connector_id` sem executar o conector.

## Consequências

- A fronteira pode ser testada sem I/O ou dependência nova.
- Cobertura mundial não pode ser habilitada por configuração vazia.
- Mudança incompatível do envelope exige novo major e decisão de
  compatibilidade do registro.
- Dados de fornecedor continuam não confiáveis e não canônicos até as futuras
  etapas de resolução, evidência e claims.
- F3.2 deverá fornecer simuladores e suíte reutilizável; F3.3 deverá implementar
  relógio, deadline, cancelamento, retry, budget e idempotência sem alterar a
  assinatura pública aqui definida.
- Conectores reais, HTTP, persistência e orquestração continuam proibidos nesta
  decisão.
