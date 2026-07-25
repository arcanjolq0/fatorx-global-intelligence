# Análise crítica do planejamento

## 1. Síntese

O planejamento acerta nos princípios essenciais — evidência, confirmação de identidade, revisão humana, risco determinístico, tolerância a falhas e pacotes por país — mas mistura visão de produto, escolhas técnicas, fontes ainda não contratadas e fases de execução. O maior risco é prometer cobertura internacional antes de validar acesso, licença, retenção e qualidade de cada fonte.

A arquitetura consolidada reduz esse risco com um núcleo modular, contratos estáveis, conectores simulados antes dos reais, fontes ativadas por gate e evidência/claims separados de risco e relatório.

## 2. Pontos fortes preservados

- decisão final humana;
- nenhuma afirmação crítica sem evidência;
- identidade antes de coleta aprofundada;
- falha parcial como resultado válido e visível;
- regras de risco versionadas;
- tradução separada do original;
- revisão de fontes e termos de uso;
- expansão de países incremental;
- testes de contrato e segurança desde o início.

## 3. Problemas arquiteturais identificados

### 3.1 Conector com responsabilidade excessiva

O exemplo original atribui ao conector `assess_entity_match` e `create_evidence`. Isso faria cada integração repetir regra de identidade, depender do modelo canônico e potencialmente persistir fatos de maneiras diferentes.

**Decisão:** o conector retorna candidatos, observações e artefatos tipados. Serviços centrais resolvem entidade, aplicam política da fonte e criam evidência. Consulte ADR-0002.

### 3.2 `SearchRun` é estreito para o domínio

O nome trata a investigação como busca técnica e mistura estado agregado com contadores de fontes. Uma investigação inclui upload, revisão, análise e relatório.

**Decisão:** usar `Investigation` como agregado; `ConnectorRun` representa cada execução. `SearchRun` fica apenas como termo histórico do plano.

### 3.3 Evidência e claim insuficientemente separados

O plano lista ambos, mas não define imutabilidade, cadeia de custódia, relação muitos-para-muitos, contradição, qualificação, revogação, política da fonte e dado derivado.

**Decisão:** contrato próprio de evidência e entidade associativa `ClaimEvidenceLink` com papel explícito. Consulte ADR-0003.

### 3.4 Estado agregado ambíguo

`COMPLETED`, `PARTIALLY_COMPLETED` e `FAILED` não possuem critérios. Também faltam cancelamento, reentrada, versão e concorrência de transições.

**Decisão:** máquina persistida com eventos, optimistic locking e regras objetivas em `investigation-lifecycle.md`.

### 3.5 Escopo de MVP excessivo

Três países, múltiplas categorias, documentos/OCR, sanções, jurídico, contatos, finanças, relatórios e autenticação formam várias linhas de produto. A disponibilidade legal e comercial de fontes é desconhecida.

**Mitigação:** separar MVP do núcleo, gates de fonte real e piloto comercial. Um país/capacidade é habilitado somente após matriz de cobertura aprovada.

### 3.6 Dependências prematuras

pgvector, Redis, automação de navegador, storage S3 e OpenSearch aparecem como arquitetura antes de métricas e requisitos operacionais. São plausíveis, não automaticamente obrigatórios.

**Decisão:** PostgreSQL e storage de objetos são baselines; fila/cache devem ser escolhidos na Fase 1 após SLA; pgvector/OpenSearch são adiados até evidência de necessidade.

### 3.7 Tenancy e autorização ausentes

O planejamento cita usuários, mas não define organização, isolamento, papéis ou compartilhamento. Isso afeta todas as tabelas, cache, storage e auditoria.

**Decisão provisória:** toda informação pertence a `workspace_id`; o MVP inicia com um workspace Fator X. Modelo comercial externo continua pendente.

### 3.8 Política temporal incompleta

Data de publicação e consulta não bastam. É necessário distinguir ocorrência, vigência, aquisição, expiração e instante de corte do relatório.

**Decisão:** timestamps semânticos separados e validade do claim/evidência explícita.

### 3.9 “Confiança” única é opaca

Misturar confiabilidade da fonte, confiança de extração e correspondência de entidade torna o número impossível de auditar.

**Decisão:** dimensões separadas; qualquer score agregado é derivado, versionado e explicável.

### 3.10 Modelo de IA no caminho crítico

O plano indica interpretação e extração, mas não define comportamento quando o modelo falha, muda ou produz saída hostil.

**Decisão:** saídas validadas por schema e tratadas como derivadas; claims críticos exigem evidência e revisão; scoring nunca depende de julgamento opaco do modelo.

## 4. Riscos prioritários

| ID | Risco | Prob. | Impacto | Mitigação / gate |
|---|---|---:|---:|---|
| R-01 | Fonte inexistente, cara ou sem direito de retenção/relatório | Alta | Crítico | catálogo e aprovação G6 antes de conector real |
| R-02 | Falso positivo de identidade ou sanção | Alta | Crítico | identificadores fortes, score dimensional e revisão humana |
| R-03 | Escopo de três países impedir validação do núcleo | Alta | Alto | implementar um pacote comercialmente priorizado por vez |
| R-04 | Claims sem cadeia de custódia | Média | Crítico | contrato de evidência, imutabilidade e testes de bloqueio |
| R-05 | Violação de privacidade/LGPD/GDPR | Média | Crítico | minimização, base legal, retenção e acesso auditado |
| R-06 | SSRF, arquivo malicioso ou navegador comprometido | Média | Crítico | egress allowlist, quarentena, sandbox e testes dedicados |
| R-07 | Prompt injection em página/documento | Alta | Alto | conteúdo como dado, ferramentas com allowlist, schema e revisão |
| R-08 | Score de risco não validado ou interpretado como decisão | Média | Crítico | metodologia aprovada, disclaimers e decisão humana |
| R-09 | Custos/latência imprevisíveis por investigação | Alta | Alto | orçamento, deadline, métricas e circuit breaker por conector |
| R-10 | Dados obsoletos ou conflitantes | Alta | Alto | temporalidade, expiração, contradições e instante de corte |
| R-11 | Falha de fila gerar duplicidade ou perda | Média | Alto | idempotência, outbox/inbox, retries e reconciliação |
| R-12 | Vazamento entre clientes/workspaces | Baixa | Crítico | workspace obrigatório, autorização e testes de isolamento |
| R-13 | OCR/conversão monetária produzir fatos incorretos | Média | Alto | preservar original, página/unidade e revisão por limiar |
| R-14 | Dependências operacionais excessivas cedo | Média | Médio | adoção justificada por métricas e ADR |
| R-15 | Relatório criar exposição jurídica | Média | Crítico | linguagem aprovada, fontes/limitações e aprovação humana |

## 5. Ambiguidades materiais

- produto interno da Fator X ou SaaS para clientes;
- definição de “fonte global” e de cobertura mínima por país;
- capacidades obrigatórias em cada nível de relatório;
- SLA, concorrência e orçamento de consulta;
- critérios numéricos de correspondência e revisão;
- metodologia, pesos e significado do score;
- retenção de originais quando a fonte proíbe armazenamento;
- significado de “contato corporativo público” e base legal;
- formato, destinatário e responsabilidade do relatório;
- idiomas suportados e revisão de tradução;
- política de atualização/reinvestigação;
- países realmente prioritários.

## 6. Dependências de execução

```text
Validação comercial/jurídica de fontes
  └─> matriz de cobertura
      └─> pacote de país
          └─> conector real
              └─> piloto de cobertura

Modelo de clientes e privacidade
  └─> tenancy + autorização + retenção
      └─> schema + storage + auditoria

Metodologia de risco
  └─> claims elegíveis + pesos + níveis
      └─> avaliação + linguagem do relatório

SLA/volume/orçamento
  └─> fila + limites + cache + observabilidade
```

## 7. Recomendação executiva

Validar primeiro uma investigação completa com simuladores e fixtures, depois uma única capacidade oficial de identidade em uma única jurisdição aprovada. Só então ampliar categorias e países. Isso preserva a visão global sem acoplar o núcleo a promessas de acesso ainda não demonstradas.
