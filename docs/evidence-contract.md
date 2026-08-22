# Contrato de evidências e claims

## 1. Objetivo

Garantir que toda conclusão material seja rastreável até conteúdo original, entidade correta, localização exata, política de uso e processo de revisão.

## 2. Conceitos

- **Artefato:** objeto original adquirido ou enviado, como JSON, HTML, PDF ou imagem.
- **Evidência:** unidade imutável e localizável dentro de um artefato ou referência externa.
- **Observação:** saída ainda não canônica de conector/extrator.
- **Claim:** afirmação estruturada sobre um sujeito, propriedade, valor e período.
- **Derivação:** transformação registrada, como OCR, tradução, extração ou cálculo.
- **Revisão:** decisão humana append-only sobre candidato, claim, risco ou relatório.

## 3. Envelope mínimo da evidência

Toda evidência precisa de:

| Grupo | Campos obrigatórios |
|---|---|
| Identidade | `evidence_id`, `workspace_id`, `investigation_id`, `subject_ref` |
| Fonte | `source_id`, `source_policy_version`, URL/identificador de origem e método de aquisição |
| Tempo | `retrieved_at`; `published_at`/vigência quando disponível, com ausência explícita |
| Conteúdo | tipo, idioma, original ou referência permitida, `content_sha256` |
| Localização | página, seção, seletor, caminho JSON, coordenada ou outro locator tipado |
| Proveniência | `artifact_id`, `connector_run_id` ou upload/revisor de origem |
| Processamento | método/versão de extração; pais da derivação quando houver |
| Identidade | política/versão de correspondência e candidato relacionado |
| Uso | admissibilidade, retenção, exibição e classificação de sensibilidade |

Campos desconhecidos não recebem valores inventados. A ausência tem razão explícita (`NOT_PROVIDED`, `NOT_APPLICABLE`, `POLICY_RESTRICTED`, `EXTRACTION_FAILED`).

## 4. Integridade e cadeia de custódia

1. Calcular SHA-256 sobre os bytes adquiridos antes de transformação.
2. Registrar instante, origem, conector/versão e política.
3. Armazenar o artefato somente no modo permitido.
4. Criar evidência com locator reproduzível.
5. Para transformação, criar nova evidência e `EvidenceDerivation`; não sobrescrever original.
6. Correção, expiração, revogação, redação e expurgo geram evento de lifecycle.
7. Relatório registra digest/versão das evidências e instante de corte usados.

Deduplicação por hash não prova independência de fontes. `origin_fingerprint` e linhagem devem indicar quando provedores reproduzem a mesma origem.

## 5. Localizadores

Tipos mínimos:

- `PAGE_TEXT`: página e intervalo/âncora textual;
- `PDF_REGION`: página e coordenadas;
- `HTML_SELECTOR`: URL, seletor e digest do documento;
- `JSON_POINTER`: caminho RFC 6901 e digest da resposta;
- `SPREADSHEET_CELL`: planilha, aba e intervalo;
- `IMAGE_REGION`: coordenadas e página/frame;
- `EXTERNAL_REFERENCE`: identificador oficial quando conteúdo não pode ser retido.

O locator deve permitir ao analista chegar ao trecho. Screenshot isolado sem origem/localização não é suficiente para claim crítico.

## 6. Traduções, OCR e resumos

- original permanece autoridade;
- tradução é derivação com idioma origem/destino, método e versão;
- OCR preserva imagem/PDF e confiança por região quando disponível;
- resumo aponta para todas as evidências usadas e não se torna evidência primária;
- saída de modelo é tratada como proposta, validada por schema;
- discrepância entre original e derivação gera warning ou revisão.

## 7. Claim estruturado

Um claim deve registrar:

- sujeito canônico ou candidato;
- `predicate_code` versionado;
- valor tipado e unidade/moeda;
- período de validade ou ocorrência;
- criticidade;
- método e versão de criação;
- confiança de extração separada de correspondência;
- status;
- links de evidência.

Papéis de link:

- `SUPPORTS`: sustenta o claim;
- `CONTRADICTS`: apresenta valor incompatível;
- `QUALIFIES`: limita escopo, tempo ou interpretação.

## 8. Admissibilidade

Estados: `PENDING`, `ADMISSIBLE`, `RESTRICTED`, `EXPIRED`, `REVOKED`, `REJECTED`.

Uma evidência é admissível somente se:

1. fonte e política estão identificadas e vigentes na aquisição;
2. uso pretendido é permitido;
3. integridade e locator são válidos;
4. sujeito possui correspondência suficiente ou revisão;
5. temporalidade é adequada à finalidade;
6. conteúdo original/referência pode ser verificado;
7. não depende somente de tradução/resumo não revisado quando crítico.

## 9. Gate de afirmação crítica

Um claim crítico pode ser apresentado como fato somente quando:

- possui ao menos uma evidência `ADMISSIBLE` ligada como `SUPPORTS`;
- atende à política de fonte mínima da categoria (por exemplo, oficialidade ou revisão), ainda a ser aprovada;
- não existe contradição crítica sem tratamento explícito;
- identidade está confirmada segundo política vigente;
- temporalidade não está expirada para o uso;
- revisão humana exigida foi concluída.

Caso contrário, o sistema deve usar linguagem de hipótese/inconclusão, mostrar a lacuna e impedir exportação factual. Número de fontes e limiares são configuração versionada, não constantes escondidas.

## 10. Confiança multidimensional

Não existe uma única “confiança” capaz de substituir explicação. Registre separadamente:

- tier/confiabilidade da fonte;
- confiança da extração;
- correspondência da entidade por dimensão;
- relevância do locator;
- atualidade/validade;
- status de revisão.

Qualquer agregado deve registrar fórmula e versão.

## 11. Contradições

Claims são potencialmente contraditórios quando compartilham sujeito, predicate e período sobreposto, mas possuem valores incompatíveis. O sistema:

1. cria grupo de conflito;
2. preserva todos os claims/evidências;
3. não escolhe silenciosamente o valor “mais confiável”;
4. permite regra determinística de precedência apenas se versionada e auditável;
5. exige revisão para conflito crítico;
6. relata a contradição e a decisão.

## 12. Exibição e relatório

O relatório deve incluir referência humana à fonte, publicação/consulta, locator, limite de uso, nível de revisão e instante de corte. Se conteúdo não puder ser redistribuído, exibir apenas o permitido e manter a referência auditável.

## 13. Testes invariantes

- hash muda quando bytes mudam;
- derivação nunca substitui pai;
- evidencia sem fonte/política/locator não vira admissível;
- claim crítico sem suporte é bloqueado;
- evidência contraditória não é descartada;
- mudança de revisão cria novo evento;
- expurgo preserva trilha permitida e remove conteúdo solicitado;
- deduplicação não confunde independência de origem;
- relatório consegue enumerar evidências exatas usadas.

## 14. Materialização inicial — F5.1

A F5.1 materializa apenas `Artifact`, versões de `Evidence` e
`EvidenceLifecycleEvent`, conforme ADR 0024. O registro exige uma decisão humana
de entidade do mesmo workspace e Investigation em `COLLECTING`; isso não cria
nova transição de lifecycle.

- bytes integrais recebidos são usados transitoriamente para SHA-256 e tamanho;
- PostgreSQL guarda metadados, locator canônico e trecho somente quando permitido;
- `OBJECT` é apenas uma referência workspace-scoped, sem adapter de storage;
- fonte e versão de política são snapshots obrigatórios, não aprovação de fonte;
- toda evidência nasce e permanece `PENDING` na F5.1;
- correção cria nova versão e `SUPERSEDED`; revogação cria evento terminal;
- correção e revogação da mesma versão-alvo são serializadas transacionalmente;
- reconstituição recalcula digests e rejeita adulteração, lacuna ou troca de escopo.

Não foram materializados claims, links, derivações, admissão, expiração, redação,
expurgo, risco ou relatório. O recibo operacional F4.6 não é promovido a
artefato ou evidência.

## 15. Materialização aceita — F5.2

A F5.2 aceita materializa `Claim` e `ClaimEvidenceLink` sem alterar a
admissibilidade global da F5.1. Toda Evidence continua `PENDING`. O link registra
a versão exata da Claim, o ID e digest exatos da Evidence, um role fechado
(`SUPPORTS`, `CONTRADICTS`, `QUALIFIES`) e uma decisão contextual produzida
exclusivamente pela política interna.

`ELIGIBLE` significa apenas que a Evidence pode ser usada na verificação interna
daquela Claim sob `F5_2_CONTROLLED_CORPUS_V1`. Exige match simultâneo de hash do
Artifact, hash do conteúdo da Evidence, kind, tipo e digest do locator, além de
`EXCERPT_ONLY`, `INDEFINITE`, `FULL` e `content_original` íntegro. Artifact
conhecido isoladamente, `source_id` e `origin_type` não concedem confiança.

Claims são imutáveis e corrigidas por nova versão contígua. Workspace,
Investigation, Company, decisão de resolução e predicate code/version não mudam
na série. Cada versão exige ao menos um `SUPPORTS`, embora seu assessment possa
ser `INSUFFICIENT`. Assessment é calculado em leitura e nunca persistido.

A reconstituição rejeita snapshots JSON não canônicos e decisões cuja
proveniência não corresponda ao ator/instante da versão. Leitura histórica
permanece disponível em `FAILED` e `CANCELLED`; mutação continua exclusiva de
`VERIFYING`. A F5.2 não implementa `ADMISSIBLE`, revisão humana, factualidade,
reportabilidade, risco, scoring, relatório ou F5.3. O ADR 0025 está `Accepted`.

## 16. Implementação candidata — F5.3

A F5.3 adiciona decisões globais imutáveis `ADMISSIBLE`, `RESTRICTED` e `REJECTED`
para uma versão exata de Evidence. O status efetivo é projetado com corte `as_of`:
ausência de decisão resulta em `PENDING`, expiração explícita resulta em `EXPIRED` e
revogação F5.1 prevalece como `REVOKED` sem efeito retroativo.

O único basis V1 é `CONTROLLED_TEST_EVIDENCE`, para purpose
`INTERNAL_FACTUAL_EVIDENCE_USE`, sob policy
`F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1`. O manifesto independente
`F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1` vincula hashes do Artifact e conteúdo,
kind, locator type e digest da canonicalização F5.1. Não há fonte real nem Gate G6.
`ADMIT` exige ator diferente de `created_by` da versão exata; `RESTRICT` e `REJECT`
podem ser aplicados pelo criador. Isso ainda não torna Claim factual ou reportável.
