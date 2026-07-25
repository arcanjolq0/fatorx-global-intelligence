# Política de fontes

## 1. Regra

Uma fonte somente pode ser usada em produção após aprovação técnica, jurídica e comercial. Existência pública de uma página não implica direito de automação, armazenamento ou redistribuição.

## 2. Estados do catálogo

- `PROPOSED`: identificada, sem autorização de implementação.
- `UNDER_REVIEW`: termos, acesso, custo e qualidade em avaliação.
- `APPROVED_TEST`: autorizada somente em ambiente/corpus de teste.
- `APPROVED_PRODUCTION`: uso produtivo no escopo exato da política.
- `SUSPENDED`: novas chamadas bloqueadas; histórico preservado conforme retenção.
- `RETIRED`: não pode ser usada por novas investigações.
- `REJECTED`: incompatível; motivo registrado.

Código de conector não muda esse estado automaticamente.

## 3. Registro obrigatório

- nome, proprietário e contato comercial;
- país/jurisdição e categorias;
- URL/endpoint e método de acesso;
- API, autenticação e ambiente de teste;
- termos, contrato, licença e data de revisão;
- custo, quota, rate limit e SLA do fornecedor;
- dados e origem primária/secundária;
- frequência de atualização e cobertura conhecida;
- armazenamento de original/trecho/hash;
- exibição interna e no relatório;
- redistribuição/exportação;
- retenção, residência e expurgo;
- dados pessoais e base legal;
- limitações, qualidade e contato de incidente;
- aprovações e vigência.

Campos desconhecidos bloqueiam produção quando materiais.

## 4. Métodos permitidos

- API oficial/licenciada;
- download/arquivo autorizado;
- página pública quando termos e automação permitirem;
- upload fornecido pelo usuário dentro de base legal/política.

Nunca quebrar CAPTCHA, autenticação, pagamento, controles técnicos ou bloqueio. Browser automation não transforma acesso proibido em permitido.

## 5. Matriz de uso

Cada versão define independentemente:

| Ação | Valores possíveis |
|---|---|
| Consultar | permitido / restrito / proibido |
| Reter original | permitido com prazo / proibido |
| Reter trecho | permitido com prazo / proibido |
| Reter hash/metadado | permitido com prazo / proibido |
| Exibir internamente | permitido / redigido / proibido |
| Incluir no relatório | citação / trecho / referência / proibido |
| Redistribuir artefato | permitido / proibido |
| Usar em modelo | permitido / proibido / somente redigido |

O sistema aplica a opção mais restritiva entre contrato, política do workspace e jurisdição.

## 6. Qualidade

Avaliar com corpus autorizado:

- cobertura e atualidade;
- precisão de identificadores;
- taxa de falso match e campos ausentes;
- consistência de datas/moedas/unidades;
- independência/origem primária;
- estabilidade do schema;
- latência, indisponibilidade e custo;
- processo de correção do fornecedor.

“Fonte confiável” não é booleano universal; tier e limitações dependem do claim/categoria.

## 7. Ativação

1. registro completo;
2. parecer jurídico/privacidade;
3. aprovação comercial/custo;
4. threat model e revisão técnica;
5. conector passa contrato e segurança;
6. qualidade atende limiar aprovado;
7. retenção/exibição configuradas e testadas;
8. observabilidade, quota e kill switch prontos;
9. feature flag habilitada primeiro em piloto.

## 8. Mudanças e suspensão

Mudança de termos, endpoint, schema, proprietário, custo ou origem cria nova versão e pode suspender uso. Erro crítico de qualidade, quebra de contrato, incidente ou expiração de aprovação aciona kill switch. Reprocessamento histórico não ocorre sem decisão registrada.

## 9. Fonte indisponível

Indisponibilidade deve resultar em estado tipado e aparecer como lacuna. O sistema não troca silenciosamente para uma fonte não aprovada nem busca atalho não autorizado.

## 10. Catálogo inicial

Nenhuma fonte real é nomeada ou considerada acessível nesta fase. O catálogo será preenchido após as respostas de `open-questions.md` e o gate G6.
