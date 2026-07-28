# Arquitetura inicial

## 1. Estilo arquitetural

O MVP será um **monólito modular com interfaces e workers assíncronos**. O objetivo é manter consistência transacional e baixa complexidade operacional sem sacrificar fronteiras que permitam extrair componentes no futuro.

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

Na F3.1, somente a fronteira tipada existe em `intelligence.connectors`. Ela
usa biblioteca padrão e pode importar IDs, país, moeda, dinheiro e UTC estáveis
do domínio; domínio, aplicação e infraestrutura não dependem da camada. O
contrato `1.0.0` define descritor, cobertura global explícita, contexto, query,
candidatos, observações, artefatos, outcomes, Protocol assíncrono e registro
instanciável. Não há adaptador, fonte, simulador, rede, execução ou persistência.

### Resolução de entidades

- normaliza candidatos;
- compara dimensões separadas;
- aplica política versionada;
- exige revisão onde necessário.

### Evidências e claims

- preserva proveniência e cadeia de custódia;
- valida política de armazenamento/exibição;
- relaciona suporte, contradição e qualificação;
- bloqueia afirmações críticas sem evidência admissível.

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

## 3. Fluxo principal

1. Usuário autorizado cria `Investigation`.
2. Sistema valida entrada e cria candidatos de identidade.
3. Política confirma automaticamente por identificador forte ou pausa para revisão.
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

- PostgreSQL é a fonte de verdade.
- A Unit of Work síncrona abre uma conexão e uma `RootTransaction`, compartilha um guard com os repositórios e exige commit explícito; saída sem commit executa rollback.
- Antes de qualquer operação, o guard comprova que não foi invalidado, conexão aberta, transação original ativa e identidade por `connection.get_transaction()`; referências capturadas não podem acionar autobegin após commit ou rollback.
- A Unit of Work invalida permanentemente o guard antes de tentar commit ou rollback. Falha do driver não reabre a fronteira; somente o `__exit__` pode executar rollback/close técnicos depois da invalidação.
- Os seis repositórios recebem o mesmo guard da Unit of Work, não abrem transações e não executam commit ou rollback. O repositório de auditoria oferece somente append.
- `UnitOfWorkFactory` cria uma instância single-use por operação; os serviços executam commit explícito, e o adaptador PostgreSQL não abre conexão durante import ou construção da factory.
- O repositório de membership expõe somente os locks e a atualização necessários ao caso de uso. Políticas de ator, alvo e papel permanecem na aplicação.
- Mudança de estado e evento a publicar usam transação única com outbox.
- Workers usam chave de idempotência e inbox/registro de processamento.
- Entrega pode ser ao menos uma vez; efeitos devem ser idempotentes.
- Transições usam versão do agregado para impedir disputa.
- Retry só ocorre para falha classificada como transitória e dentro do deadline/budget.

O produto de fila/cache não está decidido. Sua escolha deve ser registrada e justificada na Fase 1.

## 5. Dados e storage

- PostgreSQL: entidades, metadados, estados, claims, avaliações, índices e auditoria.
- Storage de objetos: documentos e payloads grandes quando a política permitir.
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
| HTTP | não decidido | F3.1 não possui rede; cliente exige fonte aprovada e decisão posterior | após F3.1/G6 |
| Web | React + TypeScript + Vite | UI tipada e separada | Fase 1 |
| Banco | PostgreSQL | transação, JSONB e busca textual | Fase 2 |
| Objetos | API compatível com S3 | artefatos grandes e retenção | Fase 5 |
| Fila/cache | não decidido | depende de SLA e operação | Fase 1/4 |
| Browser | não decidido | somente fonte aprovada que realmente exija | G6 |
| Vetores/busca externa | adiado | depende de métrica de volume/qualidade | Pós-MVP ou ADR futuro |

Itens ainda propostos nesta tabela não autorizam dependência sem a análise prevista em `AGENTS.md`. As dependências já adotadas possuem versões e análise em `docs/dependencies.md`.

## 11. Requisitos de implantação

- processos separados para API e workers, ainda que compartilhem código;
- migrations executadas como etapa controlada;
- configuração por ambiente e referências a segredos;
- health/readiness sem consultar fonte paga;
- feature flag por conector e pacote;
- rollback de aplicação compatível com schema;
- backup/restore testados antes do piloto.

## 12. Evolução

Extrair serviço somente quando medições demonstrarem necessidade independente de escala, segurança ou ownership. Candidatos naturais futuros são processamento documental e execução de navegador; a separação atual permite extração sem distribuí-los prematuramente.
