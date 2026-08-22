# Arquitetura geral

## 1. Estilo arquitetural

O MVP tem como arquitetura-alvo um **monólito modular com interfaces e workers assíncronos**. O objetivo é manter consistência transacional e baixa complexidade operacional sem sacrificar fronteiras que permitam extrair componentes no futuro.

No corte materializado até a F5.3 aceita, o monólito modular possui aplicação síncrona,
PostgreSQL, conectores simulados, execução direta controlada de uma única
operação, o núcleo canônico de evidências ainda persistido como `PENDING`, Claims com
elegibilidade estritamente contextual. Workers, fila, outbox/inbox, scheduler,
fan-out/fan-in, paralelismo, revisão factual e F5.4
continuam componentes-alvo não implementados e não autorizados.

O backend segue portas e adaptadores. O núcleo define tipos e portas; API, persistência, fila, storage, modelos e conectores são adaptadores substituíveis.

## 2. Componentes lógicos

```text
Web / API
   │
Application use cases ───────────── Audit
   │
Orchestration ──> Connector ports ──> External adapters
   │                    │
   ├─ Entity resolution │
   ├─ Evidence/Claims <─┘
   ├─ Documents
   ├─ Risk rules
   └─ Reporting
          │
PostgreSQL + Object storage + Queue adapter
```

### Núcleo de domínio

- entidades e invariantes;
- valores monetários, jurisdição, identificadores e tempo;
- claims, evidências, revisões e risco;
- ausência de imports de infraestrutura.

### Aplicação

- casos de uso;
- autorização e fronteira de transação;
- coordenação entre portas;
- emissão de eventos e auditoria.

Na F2.4.2, a aplicação recebe um `ActorContext` já autenticado por uma camada futura, valida usuário e membership ativos na mesma Unit of Work e aplica uma matriz fechada de permissões. Os serviços de Membership, Company e Investigation usam exclusivamente o workspace do contexto. Isso não cria autenticação, sessão, token, middleware ou acesso ao banco pela API.

### Orquestração

- cria plano de capacidades;
- agenda jobs independentes;
- controla budget, deadline, cancelamento e retomada;
- agrega resultados sem esconder falhas.

### Conectores

- acessam uma fonte aprovada;
- devolvem envelopes tipados e artefatos originais/referências;
- não conhecem tabelas, score ou relatório.

Desde a F3.1, a fronteira tipada existe em `intelligence.connectors`. Ela usa
biblioteca padrão e pode importar IDs, país, moeda, dinheiro e UTC estáveis do
domínio; domínio, aplicação e infraestrutura não dependem da camada. O contrato
`1.0.0` define descritor, cobertura global explícita, contexto, query,
candidatos, observações, artefatos, outcomes, Protocol assíncrono e registro
instanciável.

Na F3.2, `intelligence.connectors.simulated` contém exclusivamente um adaptador
sintético, imutável e determinístico de registro empresarial. Cenários são
selecionados explicitamente no construtor e produzem envelopes fixos, sem rede,
filesystem, ambiente, relógio, aleatoriedade ou persistência. A suíte comum
permanece em `tests/`.

Na F3.3, `intelligence.connectors.execution` controla uma única operação de um
conector fornecido explicitamente. Requests discriminadas preservam a tipagem de
busca, detalhes e documento; relógio monotônico, sleeper, jitter e idempotência
são portas injetáveis. O runner aplica preflight, deadline/cancelamento, retry,
budget, uma página, validação runtime, fingerprint, digest e eventos estruturais.
O store disponível é somente em memória e por instância. Não há seleção ou
paralelismo de conectores, planner, job, fila, persistência, HTTP ou composição
de Fase 4.

Na F4.1–F4.5, `intelligence.application` coordena comandos específicos de
lifecycle sobre portas explícitas. O domínio recebe entrada tipada e tempo
explícito e retorna snapshots/transições imutáveis. `entity_resolution` recebe
entrada, candidatos e política e retorna somente scores/ranking puros. A
infraestrutura PostgreSQL implementa CAS tenant-scoped, ledger e registros
append-only de lote/candidatos/dimensões/decisão; Company, decisão, transição e
auditoria compartilham o UoW.
O lifecycle e o matcher não importam nem chamam `intelligence.connectors`, e a
F3.3 permanece um runner local independente.

`IdentificationInput` usa JSONB apenas como envelope versionado schema `1` ou
extensão opt-in schema `2`, com
serialização canônica e digest. A aplicação não aceita payload genérico e a
auditoria não recebe conteúdo empresarial. Replay é durável por
`(workspace_id, command_id)` e advisory transaction lock; colisão de digest e
conflito de versão são erros distintos. A F4.2 persiste política/snapshot,
identidade/origem, scores e ranking, e pausa em revisão humana. A F4.3 recebe a
escolha humana explícita, materializa nova Company por política pura e avança
para `PLANNING`. A F4.4 acrescenta `orchestration.planning`: uma política pura
consome somente Investigation, Company e descritores estáticos capturados pelo
registro explícito, produz um plano `READY` e o persiste de modo append-only.
Na F4.4.1, a reconstituição separa a criação histórica do snapshot atual: as
três leituras permanecem válidas após avanço pós-confirmação se Company, lote
ativo e monotonicidade da versão continuarem coerentes. O caminho crítico usa
somente capacidades `READY`.
A F4.5 acrescenta `orchestration.collection_activation`, que consome apenas o
plano persistido, seleciona rank 1 e materializa run/operações imutáveis. O
serviço coordena CAS para `COLLECTING`, ledger e auditoria; não importa registry
nem runner. Não há job, propagação de cancelamento, endpoint ou execução de
conector.

Na F4.5.1, a fronteira pura recalcula o caminho crítico das futuras operações
`READY` usando as durações já persistidas. A aplicação valida o tempo restante
antes de gerar IDs. O adaptador PostgreSQL correlaciona cada leitura do run com
a transição histórica exata e falha fechado diante de ausência ou divergência;
a transição carrega Company e plano para tornar essa prova relacional.

Na F4.6, `application.collection_execution` liga diretamente uma única operação
`SEARCH` ao runner F3.3. O conector é injetado explicitamente, deve estar em uma
allowlist e coincidir com o descritor do manifesto; somente `TEST` é aceito. A
aplicação confirma ownership append-only antes do I/O e persiste depois um recibo
redigido sem itens/payload. O manifesto não é atualizado e nenhuma transição,
fila, worker, scheduler, outbox, descoberta ou paralelismo é introduzido.

Na F4.6.1, o descritor deixa de ser relido de forma desacoplada: o preflight
pré-commit alimenta manifesto e ownership; o runner exige que seu novo preflight
pós-commit seja idêntico antes de qualquer I/O. A confirmação de entidade também
usa lock da Investigation para auditar deterministicamente comandos distintos
que disputam a mesma versão.

Na F4.6.2, uma divergência de descritor observada após uma tentativa é terminal
e não participa da política de retry. A tentativa já iniciada pode gerar apenas
uma conclusão operacional redigida.

Na F5.1, `intelligence.evidence` materializa artefato, versões de evidência e
eventos de supersessão/revogação como registros puros e imutáveis. A aplicação
autoriza pelo workspace do ator, valida a história completa antes de qualquer
append, coordena idempotência/locks e auditoria, e a infraestrutura PostgreSQL
implementa somente a porta append-only. Fonte e política permanecem snapshots;
bytes integrais são transitórios, object storage não existe e nenhuma evidência
deixa o estado `PENDING`.

Na F5.2 aceita, `intelligence.claims` contém somente modelos puros e tipos
fechados. A aplicação coordena locks de command/Claim/Evidence, relê históricos,
aplica o manifesto sintético imutável e persiste Claim e links em um único UoW.
A infraestrutura acrescenta somente `claim` e `claim_evidence_link`; a migration
preserva a F5.1. O assessment é calculado em leitura, não persistido. O comando
não escolhe outcome, policy ou manifesto, e metadados de fonte/origem não
concedem confiança. A reconstituição exige snapshots JSON canônicos, a decisão
de cada link permanece vinculada ao ator/instante da versão, e o assessment
adquire todos os locks de Evidence em ordem antes da releitura.

### Resolução de entidades

- normaliza candidatos explicitamente fornecidos por NFKC/casefold;
- compara sete dimensões separadas com aritmética inteira;
- aplica e persiste a política versionada `ENTITY_MATCH_V1`;
- detecta conflitos fortes, ordena de forma estável e exige revisão humana;
- materializa Company somente após comando humano; não cria evidência/claim e
  não confirma o topo automaticamente.

### Evidências e claims

- preserva proveniência e cadeia de custódia;
- valida política de armazenamento/exibição;
- relaciona suporte, contradição e qualificação por versões exatas;
- calcula `INSUFFICIENT`, `SUPPORTED` ou `CONFLICTED` sem persistir verdade;
- usa `ELIGIBLE` somente para verificação interna no corpus sintético F5.2;
- mantém bloqueio futuro de afirmações críticas/reportáveis fora desta subfase.

### Documentos

- quarentena, validação, extração e OCR;
- cria observações com localização;
- nunca executa macros, links ou instruções incorporadas.

### Risco

- regras determinísticas e versionadas;
- recebe apenas claims elegíveis;
- produz explicação reproduzível;
- separa risco de qualidade/cobertura.

### Reporting

- projeção somente leitura de dados aprovados;
- inclui instante de corte, fontes, limitações e aprovação;
- não inventa nem corrige fatos.

## 3. Fluxos por horizonte

### 3.1 Fluxo materializado até a F5.2 aceita

1. Aplicação cria e avança `Investigation` por comandos tenant-scoped.
2. Matching determinístico classifica candidatos e sempre exige confirmação humana explícita.
3. Confirmação materializa uma `Company` como âncora canônica interna, ainda não como conjunto de fatos reportáveis.
4. Planner cria `InvestigationPlan`; ativação cria manifesto imutável e avança para `COLLECTING`.
5. F4.6 registra ownership durável e executa diretamente um único `SEARCH` sintético em `TEST`.
6. A execução F4.6 persiste somente a conclusão operacional redigida; seu
   payload não é transformado em evidência, claim factual, risco ou relatório.
7. Um chamador interno pode registrar evidência a partir de corpus controlado,
   ligada à decisão humana e à Investigation em `COLLECTING`; isso não consome o
   recibo F4.6 nem cria transição, claim ou admissibilidade factual.
8. Testes e chamadores internos podem reconstituir a Investigation em
   `VERIFYING`; OWNER/ADMIN registram ou corrigem Claim ligada à Evidence exata.
   A política gera a decisão contextual e Evidence permanece `PENDING`.

### 3.2 Fronteira aceita F5.3

`intelligence.evidence.admissibility` define a decisão global imutável, sua cadeia
append-only e a projeção pura por `as_of`. A aplicação valida Investigation,
entity-resolution e a versão corrente sob a ordem de locks comando → Evidence →
história de decisão. A policy `F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1` concede
`ADMISSIBLE` somente à âncora sintética exata e bloqueia self-approval. Infraestrutura
persiste apenas `evidence_admissibility_decision`; não há status materializado,
relógio no domínio, Claim review ou dependência de F5.2 para conceder trust.
Decisões reconstituídas passam por validação semântica cross-aggregate antes de read,
replay ou supersession; um digest válido não substitui a reaplicação das precondições
positivas. Leituras estabilizam Evidence e depois sua história de admissibilidade sob
a mesma ordem de locks das mutações, preservando uma projeção transacional coerente.

### 3.2 Fluxo-alvo condicionado a fases e gates futuros

1. Usuário autorizado cria `Investigation`.
2. Sistema valida entrada e cria candidatos de identidade.
3. Política apenas classifica e ordena; a confirmação é sempre humana e explícita.
4. Planner cria `InvestigationPlan` versionado por capacidades.
5. Outbox publica jobs; workers chamam conectores elegíveis.
6. Cada resultado registra status, uso, artefato e observações.
7. Normalização e resolução vinculam observações à entidade.
8. Serviço de evidência materializa evidência canônica conforme política.
9. Extratores/regras propõem claims; contradições são agrupadas.
10. Revisão humana resolve itens críticos.
11. Motor de risco calcula avaliação preliminar a partir de claims elegíveis.
12. Relatório rascunho é gerado, aprovado e exportado.

## 4. Consistência e mensageria

### 4.1 Materializado

- PostgreSQL é a fonte de verdade.
- A Unit of Work síncrona abre uma conexão e uma `RootTransaction`, compartilha um guard com os repositórios e exige commit explícito; saída sem commit executa rollback.
- Antes de qualquer operação, o guard comprova que não foi invalidado, conexão aberta, transação original ativa e identidade por `connection.get_transaction()`; referências capturadas não podem acionar autobegin após commit ou rollback.
- A Unit of Work invalida permanentemente o guard antes de tentar commit ou rollback. Falha do driver não reabre a fronteira; somente o `__exit__` pode executar rollback/close técnicos depois da invalidação.
- Todos os repositórios recebem o mesmo guard da Unit of Work, não abrem transações e não executam commit ou rollback. O repositório de auditoria oferece somente append.
- A porta de evidência oferece somente append, locks e leituras tenant-scoped;
  a aplicação valida a história agregada antes de chamar o adapter.
- A porta de Claim oferece somente locks, append inicial/correção e leituras
  tenant-scoped; não possui update, delete, replace ou commit interno.
- `UnitOfWorkFactory` cria uma instância single-use por operação; os serviços executam commit explícito, e o adaptador PostgreSQL não abre conexão durante import ou construção da factory.
- O repositório de membership expõe somente os locks e a atualização necessários ao caso de uso. Políticas de ator, alvo e papel permanecem na aplicação.
- Transições usam versão do agregado para impedir disputa.
- Retry só ocorre para falha classificada como transitória e dentro do deadline/budget.

### 4.2 Arquitetura-alvo não autorizada no corte atual

- mudança de estado e evento a publicar usam transação única com outbox;
- workers usam chave de idempotência e inbox/registro de processamento;
- entrega pode ser ao menos uma vez, com efeitos idempotentes.

O produto de fila/cache não está decidido. Sua escolha exige SLA, volume, operação e uma subfase futura explicitamente autorizada, com ADR e análise de dependência.

## 5. Dados e storage

- PostgreSQL: entidades, metadados, estados, claims, avaliações, índices e auditoria.
- Storage de objetos: componente-alvo para documentos e payloads grandes quando
  a política permitir; a F5.1 registra somente referência workspace-scoped e não
  possui adapter nem I/O de objetos.
- Hash SHA-256 sobre bytes canônicos para integridade/deduplicação técnica.
- Busca textual nativa do PostgreSQL no MVP.
- Vetores e OpenSearch ficam adiados até haver volume e caso medido.
- Storage guarda prefixo/namespace por workspace; acesso ocorre por serviço autorizado, nunca por URL pública permanente.

## 6. Isolamento e segurança

- `workspace_id` é obrigatório em toda raiz agregada e chave de storage/cache.
- Autorização é verificada no caso de uso e reforçada no adaptador de dados.
- `CompanyService` e `InvestigationService` consultam sempre por `(actor.workspace_id, resource_id)`. Recurso ausente e recurso de outro tenant são indistinguíveis publicamente.
- O autorizador contextual centraliza as consultas de usuário e membership; a política pura decide apenas papel/permissão. Restrições de alvo de ADMIN e proteção do último owner pertencem ao serviço de membership, nunca aos repositórios.
- Remoção, desativação ou rebaixamento de owner bloqueia todas as memberships `OWNER`/`ACTIVE` do workspace em ordem de ID antes da decisão. Uma transação concorrente reavalia o estado depois do primeiro commit.
- Eventos de sucesso compartilham a transação da mutação. Negações usam evento próprio e commit antes do erro seguro. Leituras bem-sucedidas não geram evento nesta fase; leituras negadas geram.
- Coleta externa usa política de egress e resolução segura de DNS/redirecionamentos.
- Browser, parsing e OCR executam isolados do núcleo e sem credenciais desnecessárias.
- Logs contêm IDs, estados, durações e códigos; conteúdo e segredos são redigidos.

## 7. Pacotes por país

O núcleo carrega pacote por código ISO e versão. O pacote fornece conhecimento local e referências a fontes aprovadas; não altera schema, não importa adaptadores e não contém segredos. Uma investigação registra a versão usada para reprodutibilidade.

## 8. Uso de modelos

O adaptador de modelo recebe apenas o mínimo necessário, com conteúdo delimitado como não confiável. A saída deve obedecer schema versionado, registrar provedor/modelo/configuração permitida e manter referências às evidências. Falha do modelo degrada a extração ou exige revisão; não altera scoring nem estado crítico por si só.

## 9. Estrutura de diretórios proposta

```text
fatorx-global-intelligence/
├── AGENTS.md
├── PLANS.md
├── README.md
├── CHANGELOG.md
├── .env.example
├── docs/
│   ├── adr/
│   └── *.md
├── apps/
│   ├── api/                    # composição e rotas FastAPI
│   └── web/                    # React/TypeScript
├── src/intelligence/
│   ├── domain/                 # tipos e invariantes
│   ├── application/            # portas e futuros casos de uso
│   ├── orchestration/          # planner e lifecycle
│   ├── entity_resolution/
│   ├── evidence/
│   ├── claims/
│   ├── documents/
│   ├── risk/
│   ├── reporting/
│   ├── connectors/             # contratos neutros; pode usar tipos estáveis do domínio
│   ├── country_packs/
│   └── infrastructure/         # DB, queue, storage, model adapters
├── workers/                     # entrypoints, sem regras próprias
├── migrations/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── security/
│   ├── end_to_end/
│   └── fixtures/
└── scripts/
```

Esta é uma proposta; diretórios de código serão criados somente na fase de implementação.

## 10. Dependências técnicas

| Área | Opção do plano | Justificativa | Gate |
|---|---|---|---|
| API | FastAPI + Pydantic | contratos tipados e ecossistema Python | Fase 1 |
| Persistência | SQLAlchemy Core 2.x + Alembic + Psycopg 3 síncrono | metadata/migrations explícitas e adaptadores sem ORM; Unit of Work controla a transação | Fase 2 — ADR-0010 e ADR-0011 |
| HTTP | não decidido | F3.3 não possui rede; cliente exige fonte aprovada e decisão posterior | após G6 |
| Web | React + TypeScript + Vite | UI tipada e separada | Fase 1 |
| Banco | PostgreSQL | transação, JSONB e busca textual | Fase 2 |
| Objetos | API compatível com S3 | artefatos grandes e retenção | Fase 5 |
| Fila/cache | não decidido | depende de SLA e operação | subfase futura autorizada |
| Browser | não decidido | somente fonte aprovada que realmente exija | G6 |
| Vetores/busca externa | adiado | depende de métrica de volume/qualidade | Pós-MVP ou ADR futuro |

Itens ainda propostos nesta tabela não autorizam dependência sem a análise prevista em `AGENTS.md`. As dependências já adotadas possuem versões e análise em `docs/dependencies.md`.

## 11. Requisitos-alvo de implantação

Os itens abaixo pertencem ao MVP-alvo; não descrevem componentes já materializados na F5.1.

- processos separados para API e workers, ainda que compartilhem código;
- migrations executadas como etapa controlada;
- configuração por ambiente e referências a segredos;
- health/readiness sem consultar fonte paga;
- feature flag por conector e pacote;
- rollback de aplicação compatível com schema;
- backup/restore testados antes do piloto.

## 12. Evolução

Extrair serviço somente quando medições demonstrarem necessidade independente de escala, segurança ou ownership. Candidatos naturais futuros são processamento documental e execução de navegador; a separação atual permite extração sem distribuí-los prematuramente.
