# Requisitos consolidados do produto

## 1. Propósito

O Fator X Global Intelligence deve apoiar analistas na investigação de pessoas jurídicas internacionais, reunindo dados autorizados, resolvendo identidade, preservando evidências e produzindo análise e relatórios auditáveis. A decisão final pertence a uma pessoa autorizada.

## 2. Personas iniciais

- **Analista:** inicia investigação, confirma entidade, revisa claims, avalia limitações e aprova relatório.
- **Revisor:** valida ocorrências críticas e aprovação final conforme alçada.
- **Administrador:** gerencia usuários, políticas, pacotes habilitados e acesso; não altera evidência.
- **Auditor:** consulta trilha e versões sem poder modificar resultados.

A existência de usuários clientes externos não está decidida e permanece em `open-questions.md`.

## 3. Casos de uso do MVP

1. Criar investigação com empresa, país e identificadores disponíveis.
2. Gerar candidatos antes de coleta aprofundada.
3. Confirmar ou rejeitar candidato quando a política exigir.
4. Planejar capacidades dentro do pacote, orçamento e fontes aprovadas.
5. Executar conectores de forma assíncrona e tolerante a falha.
6. Preservar artefatos e metadados permitidos pela política da fonte.
7. Normalizar observações e vinculá-las à entidade correta.
8. Criar claims rastreáveis, sinalizar contradições e exigir revisão crítica.
9. Anexar e processar documentos de forma segura.
10. Calcular risco preliminar por regras versionadas.
11. Produzir relatório com fatos, limitações, ausências e fontes.
12. Consultar histórico e auditoria.

## 4. Requisitos funcionais

### RF-01 — Autorização

Toda operação deve pertencer a um `workspace_id`. Ações de leitura, revisão, aprovação e exportação exigem permissões explícitas e geram eventos de auditoria.

### RF-02 — Identificação da entidade

A coleta aprofundada fica bloqueada até que a entidade atinja o estado permitido pela política: confirmação automática por identificador forte ou confirmação humana. Similaridade de nome isolada nunca basta para ocorrência crítica.

### RF-03 — Planejamento de capacidades

O plano de investigação deve registrar perfil solicitado, capacidades, país, conectores elegíveis, obrigatoriedade, deadline, orçamento e motivo de inclusão/exclusão.

### RF-04 — Execução tolerante a falhas

Cada execução de conector é independente e idempotente. Falha, indisponibilidade ou bloqueio de uma fonte produz resultado explícito; não apaga resultados válidos das demais.

### RF-05 — Proveniência

Todo dado usado como fato deve apontar para um claim e pelo menos uma evidência admissível. A cadeia deve chegar à fonte e à localização exata do conteúdo original.

### RF-06 — Contradições

Claims incompatíveis sobre a mesma propriedade, entidade e período devem ser agrupados e apresentados como conflito até decisão humana ou regra explícita.

### RF-07 — Documentos

Uploads permanecem em quarentena até validação. Extrações preservam documento, página ou região, idioma, método e versão do extrator. OCR não substitui o artefato original.

### RF-08 — Risco preliminar

O resultado deve ser reproduzível a partir de uma versão imutável da metodologia, claims elegíveis e parâmetros. Qualidade de dados e dados ausentes aparecem separados da categoria de risco.

### RF-09 — Revisão

Claims críticos, correspondências ambíguas e relatórios finais devem suportar confirmação, rejeição, justificativa, autor e instante. A revisão não modifica a evidência.

### RF-10 — Relatório

O relatório deve declarar entidade, escopo, instante de corte, metodologia, fatos e fontes, alertas, contradições, ausências, limitações, estado de revisão e aprovação.

### RF-11 — Auditoria

Criar trilha append-only para acesso sensível, mudanças de estado, revisão, política, avaliação, geração e exportação de relatório.

### RF-12 — Pacotes de país

Seleção de identificadores, normalização, termos e capacidades deve ocorrer por pacote versionado. País sem pacote compatível permanece explicitamente não suportado.

## 5. Requisitos não funcionais

- **RNF-01 Tipagem:** tipos explícitos no backend e modo estrito no TypeScript; payload externo validado na borda.
- **RNF-02 Segurança:** menor privilégio, criptografia em trânsito, segredos externos, proteção SSRF e upload seguro.
- **RNF-03 Auditabilidade:** correlação ponta a ponta e versões de políticas, conectores, extratores e regras.
- **RNF-04 Resiliência:** idempotência, retry limitado, deadlines, cancelamento e conclusão parcial.
- **RNF-05 Reprodutibilidade:** resultado derivado pode ser recalculado com mesmas entradas e versões.
- **RNF-06 Observabilidade:** métricas de latência, falhas, custo e cobertura sem vazar conteúdo sensível.
- **RNF-07 Internacionalização:** Unicode, idiomas registrados, ISO 3166-1 alfa-2, ISO 4217 e instantes UTC.
- **RNF-08 Acessibilidade:** interface operável por teclado e sem depender apenas de cor para estados críticos.
- **RNF-09 Retenção:** políticas por workspace, fonte e classe de dado, com expurgo auditável.
- **RNF-10 Escalabilidade:** jobs longos fora do request web; busca especializada somente após medição.

## 6. Categorias críticas

Por padrão, são críticas: sanções, insolvência ativa, fraude, crime, beneficiário sancionado, recusa de crédito, identidade contestada e qualquer alegação que possa causar dano material. A lista é política versionada, não enum fixo na interface.

## 7. Fora do MVP

- decisão ou concessão automática de crédito;
- limite financeiro definitivo;
- monitoramento contínuo em massa;
- CRM, cobrança e envio automático ao cliente;
- pesquisa de dados privados ou pessoais sem base legal;
- cobertura genérica de país sem pacote e fontes aprovadas;
- OpenSearch ou vetor sem caso medido;
- automação para contornar barreiras de acesso.

## 8. Premissas provisórias

- A operação inicial ocorre em um workspace da Fator X, preservando fronteira para futuros workspaces.
- O produto inicial é assíncrono e voltado a desktop web.
- PostgreSQL é a fonte de verdade de metadados e registros; artefatos grandes ficam em storage de objetos.
- Fontes, SLAs, preços, retenção e metodologia final ainda dependem de validação.

## 9. Rastreabilidade

Cada RF deve receber testes identificados e ligação ao critério correspondente em `mvp-definition-of-done.md` quando implementado. Mudança de requisito crítico exige atualizar riscos e, se arquitetural, ADR.
