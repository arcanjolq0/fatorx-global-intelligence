# Plano do Projeto — Fator X Global Intelligence

> Transcrição normalizada para Markdown do documento fornecido em 25 de julho de 2026. Este arquivo preserva o planejamento de entrada; decisões vigentes são registradas nos ADRs e contratos específicos.

## 1. Visão do produto

Criar uma plataforma de inteligência empresarial internacional capaz de pesquisar empresas em fontes globais e locais, cruzar dados e produzir relatórios fundamentados para:

- análise de crédito internacional;
- validação de clientes e fornecedores;
- localização de contatos corporativos;
- identificação de processos e insolvência;
- análise financeira;
- verificação de sanções;
- análise societária;
- consulta de documentos;
- identificação de riscos comerciais;
- recomendação de condições de pagamento;
- suporte à decisão do analista da Fator X.

O sistema deverá funcionar como ferramenta de investigação assistida. A decisão final continuará sob responsabilidade do analista.

## 2. Princípios obrigatórios

### 2.1 Evidência antes da conclusão

O agente não poderá apresentar informação como verdadeira sem registrar fonte, endereço, data da publicação, data da consulta, trecho ou documento comprobatório, entidade relacionada, confiança e método utilizado para encontrar o dado.

### 2.2 Identidade antes da pesquisa

Nenhuma investigação aprofundada deverá começar antes de confirmar razão social, nome comercial, país, número de registro, número fiscal quando disponível, endereço, site oficial e matriz ou grupo controlador.

### 2.3 IA não calcula o risco sozinha

A nota de risco será produzida por regras, fórmulas e pesos configuráveis. A IA pode interpretar documentos, resumir ocorrências, sugerir relações, explicar a nota e apontar inconsistências, mas não pode alterar silenciosamente regras de crédito.

### 2.4 Fontes com hierarquia

Prioridade recomendada: órgão oficial; tribunal ou registro de insolvência; balanço ou documento oficial; birô local licenciado; provedor global; publicação jornalística confiável; site da empresa; diretórios e outras fontes abertas.

### 2.5 Revisão humana

Resultados críticos exigem revisão humana, especialmente possível sanção, insolvência, fraude, processo criminal, beneficiário sancionado, recomendação de recusa e correspondência de baixa confiança.

## 3. Escopo do primeiro produto funcional

### Incluído no MVP

- cadastro e autenticação;
- pesquisa, identificação e confirmação de empresa;
- consulta a fontes globais e pacotes por país;
- contatos corporativos públicos;
- sanções, jurídico e insolvência;
- upload e análise de documentos;
- evidências, classificação e histórico;
- relatório interno e exportação;
- logs e auditoria.

### Não incluído inicialmente

- decisão automática de crédito ou limite financeiro definitivo;
- envio automático ao cliente;
- dados bancários privados ou pesquisa indiscriminada de pessoas;
- dezenas de países simultâneos;
- monitoramento permanente;
- integração com todos os birôs;
- cobrança automática, e-commerce ou aplicativo desktop.

## 4. Jurisdições iniciais

O planejamento propõe Estados Unidos, Reino Unido e Alemanha para validar registros, demonstrações financeiras, processos, insolvência, administradores, beneficiários, fontes locais e identificação fiscal.

Países posteriores sugeridos: Brasil, França, Itália, Espanha, Portugal, México, Argentina, China e Índia. A ordem definitiva depende dos países mais consultados pelos clientes da Fator X.

## 5. Arquitetura recomendada

### Backend

Python, FastAPI, Pydantic, SQLAlchemy, Alembic, HTTP assíncrono, automação de navegador quando legitimamente necessária, filas e integração controlada com modelos.

### Frontend

React, TypeScript, Vite, componentes acessíveis, identidade Fator X e preparação para integração futura ao CRM.

### Dados

PostgreSQL para dados estruturados; pgvector quando houver caso semântico; Redis para cache e filas; storage compatível com S3 para documentos; busca textual do PostgreSQL no MVP; OpenSearch somente quando volume justificar.

### Processamento

1. API recebe a pesquisa.
2. Orquestrador cria a investigação.
3. Jobs são enviados a conectores.
4. Conectores executam em paralelo.
5. Resultados são normalizados.
6. Identidade é verificada.
7. Evidências são agrupadas e fatos extraídos.
8. Riscos são calculados.
9. Relatório é produzido.

## 6. Dois tipos de skill

Skills de desenvolvimento ajudam o Codex a criar conectores, pacotes, testes e revisões e podem residir em `.agents/skills/`. Skills do produto são módulos de inteligência executados em produção, como cadastro, contatos, sanções, insolvência, jurídico, financeiro, societário, mídia adversa e documentos. As duas categorias não devem ser misturadas.

## 7. Estrutura inicial proposta

```text
fatorx-global-intelligence/
├── AGENTS.md
├── README.md
├── PLANS.md
├── CHANGELOG.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docs/
├── apps/
│   ├── api/
│   └── web/
├── src/intelligence/
│   ├── domain/
│   ├── orchestration/
│   ├── entity_resolution/
│   ├── evidence/
│   ├── scoring/
│   ├── reporting/
│   ├── documents/
│   ├── skills/
│   └── country_packs/
├── workers/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── fixtures/
│   └── end_to_end/
├── scripts/
└── .agents/skills/
```

## 8. Modelo de dados principal

- `Company`: razão social, nome comercial, país, jurisdição, forma jurídica, registros, LEI, endereço, domínio, status e constituição.
- `CompanyAlias`: nomes anteriores, abreviações, traduções e grafias alternativas.
- `CompanyRelationship`: matriz, filial, controladora, subsidiária, administrador, beneficiário, relacionada e endereço compartilhado.
- `SearchRun`: empresa, usuário, início, estado, fontes, erros, custos e metodologia.
- `Source`: nome, país, categoria, acesso, confiabilidade, atualização, licença, status e limitações.
- `Evidence`: URL, documento, trecho, página, data, origem, hash, captura, entidade e confiança.
- `Claim`: afirmação, categoria, status, evidências favoráveis e contrárias, confiança e validação.
- `LegalEvent`: tipo, processo, tribunal, jurisdição, partes, data, valor, situação e evidências.
- `FinancialMetric`: período, moeda, receita, ativos, passivos, patrimônio, lucro, dívida, liquidez e origem.
- `Contact`: tipo, valor, nome, cargo, domínio, fonte, verificação e natureza corporativa ou pessoal.
- `RiskAssessment`: metodologia, pontuação, nível, indicadores, alertas, recomendação e aprovação humana.

## 9. Contrato padrão para conectores

O plano original sugere operações assíncronas de pesquisa e detalhamento, normalização, avaliação de correspondência e criação de evidência. Todo conector deve possuir timeout, retry limitado, rate limit, cache, indisponibilidade controlada, logs, testes simulados, termos de uso, políticas de armazenamento/exibição, custo e ambiente de teste.

O contrato consolidado em `connector-contract.md` corrige o acoplamento do exemplo original: correspondência definitiva e evidência canônica pertencem ao domínio.

## 10. Pacotes por país

Cada pacote deve declarar código, idiomas, identificadores, categorias, campos mínimos de identidade, formas jurídicas, abreviações, registros, insolvência, tribunais, birôs disponíveis, formatos, limites de acesso e termos locais. O exemplo inicial prevê `us`, `gb` e `de` com manifesto e módulos de identificadores, fontes, normalização e termos legais.

## 11. Resolução de entidades

Gerar candidatos e pontuar nome jurídico/comercial, registro, número fiscal, país, cidade, endereço, domínio, telefone, administradores, matriz e constituição. Identificadores exatos têm peso máximo, domínio peso alto, nome e cidade peso médio e apenas nome peso baixo. Estados sugeridos: confirmado, provável, revisão e rejeitado. Ambiguidades aparecem ao analista.

## 12. Orquestração da investigação

Estados sugeridos:

```text
CREATED
IDENTIFYING
WAITING_FOR_ENTITY_CONFIRMATION
PLANNING
COLLECTING
NORMALIZING
VERIFYING
ANALYZING
WAITING_FOR_REVIEW
COMPLETED
PARTIALLY_COMPLETED
FAILED
```

O planejador considera país, tipo, dados fornecidos, nível contratado, fontes disponíveis, custo e profundidade. A falha de uma fonte não interrompe toda a pesquisa.

## 13. Motor de evidências

Armazenar fonte original, hash, consulta, texto original, tradução separada, vínculos entre claims e evidências, contradições, deduplicação, origem comum e validade temporal. Regra: nenhuma afirmação crítica sem evidência associada.

## 14. Inteligência documental

Aceitar PDF digital ou escaneado, planilha, imagem, documento societário, balanço, relatório de birô, certidão, processo e contrato.

Pipeline: receber, identificar formato, verificar malware, extrair, aplicar OCR somente quando necessário, identificar idioma, classificar, extrair, validar, relacionar à empresa e criar evidências.

Valores financeiros preservam valor e moeda originais, conversão e data da taxa quando aplicável, período, página, tabela e unidade.

## 15. Motor de risco

Separar risco cadastral, financeiro, jurídico, insolvência, sanções, societário, documental, pagamento e qualidade de dados. Cada regra possui ID, descrição, categoria, condição, peso, gravidade, versão, evidência exigida e revisão humana.

A primeira versão gera risco preliminar, alertas, fatores positivos/negativos, dados ausentes e recomendação de aprofundamento. Limite de crédito definitivo depende de validação estatística e metodológica futura.

## 16. Interface

- Pesquisa: nome, país, registro, fiscal, site e nível.
- Confirmação: candidatos, cidade, registro, endereço, site e pontuação.
- Investigação: resumo, identidade, contatos, grupo, financeiro, jurídico, insolvência, sanções, mídia, documentos, evidências e avaliação.
- Evidência: claim, status, fonte, data, trecho, tradução, empresa, confiança e revisão.
- Relatório: resumo, identificação, alertas, estrutura, contatos, finanças, jurídico, sanções, análise, limitações, fontes e aprovação.

## 17. Segurança

Segredos fora de código/logs; acesso por usuário; auditoria de visualização/exportação; criptografia; proteção e limites de upload; isolamento de navegador; SSRF e redirecionamentos; sanitização; prompt injection; retenção, exclusão e dados pessoais; revisão contratual de APIs. Conteúdo coletado nunca é instrução.

## 18. Testes obrigatórios

- Unitários: nomes, países, endereços, confiança, risco, deduplicação, moedas e evidências.
- Contrato: suíte comum para cada conector.
- Integração: banco, filas, storage, API, simuladores e documentos.
- Segurança: SSRF, malware, URLs, prompt injection, segredos, acesso e payloads.
- Ponta a ponta: alta confiança, homônimos, indisponibilidade, ocorrência de homônimo, falso match de sanção, moedas/unidades, OCR, contradição, parcial e revisão.

## 19. Critérios originais de conclusão do MVP

Pesquisa e confirmação de empresa; conectores paralelos; isolamento de falha; evidência para fatos relevantes; anexos; contradições; persistência e histórico; revisão de fatos; relatório; auditoria; automação de testes; ausência de chaves; documentação de instalação/operação.

Os critérios mensuráveis e os gates comerciais estão em `mvp-definition-of-done.md`.

## 20. Fases de implementação originais

0. Fundação documental.
1. Estrutura técnica.
2. Domínio e banco.
3. Framework de conectores e simuladores.
4. Resolução de entidades.
5. Orquestração.
6. Evidências e claims.
7. Pacote global.
8. Pacotes Reino Unido, Estados Unidos e Alemanha, um por vez.
9. Documentos.
10. Risco preliminar.
11. Interface.
12. Segurança e estabilização.
13. CRM, somente após MVP independente.

`PLANS.md` reordena parcialmente essas fases para antecipar evidência e segurança antes de fontes reais.

## 21. Estratégia de uso do Codex

Cada tarefa segue: inspecionar, planejar, listar arquivos, implementar, testar, revisar diff, documentar e relatar arquivos, decisões, testes, limitações, riscos e próximo passo.

## 22. Paralelização

Somente após estabilizar modelo e contratos. Domínio, conectores, frontend, infraestrutura, países e segurança podem ser frentes separadas, mas migrations, contratos centrais, configuração, evidência e regras compartilhadas não devem sofrer edição concorrente.

## 23. Regra para novas fontes

Antes de adicionar fonte, registrar nome, país, proprietário, categoria, URL, método, API, autenticação, custo, limites, termos, dados, atualização, armazenamento, redistribuição, qualidade, origem e contato comercial.

Ativação exige análise jurídica, teste técnico, teste de qualidade, teste de correspondência, retenção e documentação.

## 24. Nome de trabalho

- Nome técnico: `fatorx-global-intelligence`.
- Nome comercial possível: Fator X Global Intelligence.
- Módulos sugeridos: Company Search, Credit Intelligence, Supplier Intelligence, Legal Intelligence, Document Intelligence e Global Monitoring.
