# ADR 0024 — Núcleo canônico de evidências

- Status: Accepted — revisão independente concluída com correções em 2026-08-21
- Data: 2026-08-14
- Decisores: responsável pelo projeto e revisão independente da F5.1
- Relacionados: ADR 0003, ADR 0007, ADR 0008, ADR 0011, ADR 0013 e ADR 0023

## Contexto

O contrato de evidências exige conteúdo original ou referência permitida, hash,
fonte, política, tempo, locator reproduzível, vínculo com a entidade correta e
correções auditáveis. O repositório ainda não materializa `SourceDefinition`,
`SourcePolicyVersion`, `ConnectorRun` ou storage de objetos e não autoriza fonte
real, HTTP, jobs ou novas transições do lifecycle.

A F5.1 precisa materializar a cadeia de custódia sem transformar resultados da
F4.6 em fatos, sem inventar aprovação de fonte e sem antecipar claims,
admissibilidade, derivações, risco ou relatório.

## Decisão

1. O núcleo puro `intelligence.evidence` contém três registros imutáveis:
   `Artifact`, versões de `Evidence` e `EvidenceLifecycleEvent`.
2. `Artifact` preserva escopo, origem, fonte e versão de política como snapshot,
   método/versão de aquisição, instantes, tipo de mídia, SHA-256 e tamanho dos
   bytes originais, `origin_fingerprint` e políticas fechadas de storage,
   retenção, exibição e sensibilidade. Os bytes usados no hash são transitórios
   e não fazem parte do registro ou do `repr`.
3. Os modos `OBJECT`, `EXCERPT_ONLY`, `REFERENCE_ONLY` e
   `EPHEMERAL_PROCESSING` são vocabulário de política. F5.1 não implementa
   object storage: `OBJECT` aceita apenas uma referência já fornecida e
   prefixada pelo workspace; não prova que o objeto existe e não executa I/O.
4. `Evidence` é uma unidade exatamente localizável. Os locators mínimos são
   tipos fechados: `PAGE_TEXT`, `PDF_REGION`, `HTML_SELECTOR`, `JSON_POINTER`,
   `SPREADSHEET_CELL`, `IMAGE_REGION` e `EXTERNAL_REFERENCE`.
5. Toda evidência aponta para uma `EntityResolutionDecision` confirmada e para a
   mesma Company, Investigation e workspace por FK composta. ID e versão da
   política de matching são copiados da decisão; o cliente não os escolhe.
6. A F5.1 cria somente admissibilidade `PENDING`. Nenhum serviço admite,
   rejeita ou usa evidência para produzir claim.
7. Correção cria nova linha no mesmo `series_id`, versão contígua e evento
   `SUPERSEDED/CORRECTION`. Revogação cria um único evento terminal `REVOKED`.
   Não existem update/delete nas portas. Se o artefato estiver errado, o fluxo
   seguro é revogar a série e registrar outra, não trocar sua custódia.
8. Registro e correção exigem Investigation em `COLLECTING` e identidade já
   confirmada; isso não cria transição. Revogação é um controle corretivo
   autorizado e pode ocorrer depois, sem reabrir o lifecycle.
9. Comandos usam idempotência tenant-scoped, lock transacional por comando e,
   nas mutações de histórico, lock adicional por versão-alvo. Assim, correção e
   revogação concorrentes não podem formar uma história contraditória. O digest
   inclui hashes em vez de payload. Registro/correção são permitidos a analyst,
   admin e owner; leitura inclui viewer; revogação é limitada a admin/owner.
10. PostgreSQL guarda metadados, locators canônicos e somente o trecho original
    permitido. Reconstituição recalcula digests e valida toda a série e eventos;
    ausência, adulteração, regressão temporal ou troca de escopo falham fechado.
11. Auditoria de aplicação usa o recurso `INVESTIGATION` já aceito e não recebe
    conteúdo, origem, locator ou dado pessoal. O evento de lifecycle é a trilha
    específica da correção/revogação.
12. Nenhuma dependência foi adicionada.

## Consequências

- A cadeia de custódia canônica passa a existir sem acoplar conectores ou banco
  ao núcleo.
- Tenancy é defendida por autorização, filtros tenant-first e FKs compostas,
  inclusive nos vínculos de série, supersessão e evidência relacionada.
- Hash prova integridade do conteúdo recebido; não prova veracidade,
  independência da origem, licenciamento ou existência de objeto externo.
- Fonte e política são snapshots obrigatórios, ainda sem FK para um catálogo que
  não existe. Isso não aprova nem ativa fonte real.
- `content_original` pode existir apenas quando a política permite; bytes
  integrais de artefato não são persistidos no PostgreSQL pela F5.1.

## Alternativas rejeitadas

- **Uma tabela única para artefato e evidência:** mistura aquisição com trecho e
  enfraquece cadeia de custódia.
- **Atualizar a linha corrigida:** destrói auditabilidade e replay.
- **Tratar o recibo F4.6 como evidência:** ele exclui deliberadamente payload e
  observações e não satisfaz o contrato.
- **Criar catálogo de fontes ou object storage agora:** expande o escopo e exige
  decisões técnicas, jurídicas e comerciais ainda abertas.
- **Marcar evidência admissível no registro:** antecipa política e revisão que
  pertencem a subfase posterior.

## Critério para `Accepted`

O status só muda para `Accepted` após suíte completa, gates estáticos, build,
scanner, ZIP limpo e parecer independente binário `ACEITAR` para a F5.1.

## Aceite independente

Em 2026-08-21, a revisão da tag candidata `f5.1-review-candidate` identificou e
corrigiu atomicidade de validação antes do append, auditoria dos caminhos de
falha, fechamento de discriminadores/JSON Pointer e a constraint de bytes
originais. A repetição focal, a suíte integral, PostgreSQL real, migrations,
gates estáticos, scanner, builds e pacote criado somente de arquivos rastreados
foram aprovados. O parecer binário é **ACEITAR**, com registro operacional
`APPROVED_WITH_FIXES`. Este aceite não autoriza F5.2 nem fecha o Gate E2E.
