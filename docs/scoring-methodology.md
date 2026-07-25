# Metodologia de risco preliminar

## 1. Princípio

Risco é calculado por regras determinísticas, versionadas, aprovadas e reproduzíveis. Modelo de IA pode explicar as regras disparadas em linguagem natural, mas não escolhe peso, altera resultado ou decide crédito.

## 2. Entradas elegíveis

Somente entram no cálculo:

- claims no status permitido pela metodologia;
- evidências admissíveis e dentro da validade;
- entidade confirmada;
- decisões de revisão vigentes;
- dados derivados com método e versão conhecidos.

Texto livre, observação de conector, score de similaridade bruto ou resposta de modelo não são entradas diretas.

## 3. Dimensões separadas

- cadastral;
- financeira;
- jurídica;
- insolvência;
- sanções;
- societária;
- documental;
- pagamento;
- qualidade/cobertura de dados.

Qualidade/cobertura não deve inflar automaticamente risco. Um resultado inconclusivo precisa ser distinguível de risco alto.

## 4. Versão de metodologia

Cada versão registra:

- ID e versão imutável;
- vigência e status (`DRAFT`, `APPROVED`, `RETIRED`);
- categorias e escalas;
- regras e ordem/prioridade;
- política de claims/evidências elegíveis;
- tratamento de ausência e contradição;
- mapeamento de score para nível;
- revisões e vetos humanos;
- aprovador e digest da definição.

Investigação guarda a versão usada. Reprocessar com versão nova cria avaliação nova, preservando a anterior.

## 5. Regra

Campos mínimos:

- `rule_code` estável;
- categoria e descrição;
- condição declarativa sobre fatos tipados;
- gravidade;
- impacto decimal ou efeito categórico;
- limites e unidade;
- evidência mínima;
- comportamento com dado ausente/conflitante;
- exigência de revisão;
- versão e testes de exemplos.

Condições não executam código arbitrário vindo de usuário, fonte ou modelo.

## 6. Pipeline

1. congelar snapshot de claims elegíveis;
2. validar metodologia aprovada;
3. avaliar cada regra de forma determinística;
4. registrar `TRIGGERED`, `NOT_TRIGGERED`, `NOT_APPLICABLE` ou `INSUFFICIENT_DATA`;
5. calcular dimensões e agregação aprovada;
6. calcular qualidade/cobertura separada;
7. aplicar somente overrides humanos previstos, com justificativa;
8. persistir digest, resultados e explicação determinística;
9. gerar texto explicativo apenas a partir desses resultados.

## 7. Sanções e eventos críticos

Possível correspondência de sanção não é confirmação. Ela passa por resolução de identidade e revisão obrigatória. Regras podem bloquear exportação ou exigir escalonamento, mas a política final precisa de aprovação de compliance.

## 8. Ausência e contradição

- ausência gera `INSUFFICIENT_DATA` ou `NOT_APPLICABLE` conforme regra;
- contradição crítica não é resolvida por média de confiança;
- metodologia pode suspender categoria ou exigir revisão;
- relatório mostra impacto da ausência e limitações.

## 9. Papel do modelo

Permitido: converter resultados estruturados em explicação, resumir evidências citadas e sugerir questões para analista.

Proibido: inventar regra, usar conhecimento não evidenciado, escolher versão, modificar score, declarar match crítico ou emitir decisão final.

Explicação gerada deve ser validada contra lista de regras/claims e conter links de evidência. Se validação falhar, usar explicação determinística por template.

## 10. Validação antes de produção

É necessário definir com especialistas:

- dataset autorizado e representativo;
- métricas por categoria e país;
- falsos positivos/negativos toleráveis;
- calibração e estabilidade temporal;
- fairness e efeitos sobre grupos/mercados;
- linguagem e responsabilidade do relatório;
- processo de aprovação e mudança.

Até essa validação, o resultado chama-se **risco preliminar**, não limite nem decisão de crédito.

## 11. Testes

- golden cases por versão;
- propriedades de limites, ordem e arredondamento;
- mesma entrada/versão gera mesmo digest/resultado;
- dinheiro nunca passa por float;
- claim inelegível não afeta score;
- ausência e contradição seguem política;
- modelo indisponível não muda score;
- override exige alçada, justificativa e auditoria;
- versão aprovada é imutável.
