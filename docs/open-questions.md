# Perguntas pendentes de validação

As respostas devem registrar responsável, data, decisão e documentos afetados. Itens marcados como bloqueadores impedem o gate indicado em `PLANS.md`.

## Comercial e produto

1. **Bloqueador G1:** o MVP será ferramenta exclusivamente interna da Fator X ou terá usuários clientes externos?
2. **Bloqueador G6:** qual jurisdição deve ser a primeira com fonte real: Estados Unidos, Reino Unido ou Alemanha?
3. Quais países representam 80% das consultas atuais e qual volume mensal esperado por país?
4. Quais capacidades são obrigatórias em cada nível de relatório: identidade, contatos, finanças, jurídico, insolvência, sanções, societário, mídia e documentos?
5. Qual orçamento máximo por investigação e por fonte?
6. Qual SLA para resultado inicial, parcial e final?
7. O cliente pode receber relatório com cobertura parcial? Quem aceita a exceção?
8. Qual formato de exportação e identidade visual são necessários no piloto?
9. Quais dados devem ser enviados futuramente ao CRM e qual sistema é o CRM alvo?

## Fontes, licenças e jurídico

10. **Bloqueador G6:** quais fontes já possuem contrato, credenciais de teste e autorização de armazenamento/exibição?
11. Para cada fonte, pode-se guardar payload original, trecho, screenshot ou apenas referência/hash?
12. Há direito de redistribuir conteúdo no relatório ao cliente?
13. Qual retenção contratual e territorial por fonte?
14. Quais fontes exigem atribuição, avisos ou auditoria de uso?
15. Qual base legal e política para contatos nominativos, administradores e beneficiários?
16. Quais jurisdições exigem residência ou transferência internacional específica?
17. Qual linguagem jurídica deve acompanhar sanções, processos, fraude e recomendação de crédito?

## Crédito e metodologia

18. **Bloqueador G7:** quem é o dono formal da metodologia de risco?
19. Quais categorias, pesos, níveis e regras de veto serão aprovados?
20. Que evidência é obrigatória por claim crítico e quando duas fontes são exigidas?
21. Qual limiar de correspondência permite confirmação automática e qual sempre exige revisão?
22. Como tratar empresa sem dados: risco alto, resultado inconclusivo ou qualidade baixa separada?
23. Quando um claim ou relatório expira e exige nova consulta?
24. A recomendação de condições de pagamento faz parte do piloto ou é pós-validação estatística?

## Operação e segurança

25. **Bloqueador G1:** quais papéis, alçadas e segregação de funções são necessários?
26. Qual provedor de identidade será usado e existe SSO obrigatório?
27. Qual retenção de investigações, evidências, documentos, relatórios e logs?
28. Quem pode visualizar/exportar dados pessoais e documentos licenciados?
29. Quais requisitos de backup, RPO, RTO e resposta a incidentes?
30. Há regiões de hospedagem obrigatórias?
31. Quais navegadores e requisitos de acessibilidade são suportados?
32. Quem revisa e aprova novas fontes e pacotes de país?

## Inteligência documental e IA

33. Quais tipos e tamanhos máximos de documento são reais no fluxo atual?
34. Quais idiomas e qualidade mínima de OCR são necessários?
35. Dados podem ser enviados a provedores de modelo externos? Em quais regiões e com qual retenção?
36. Qual taxa aceitável de revisão humana para extrações e traduções?
37. Qual política de versão e reprocessamento quando modelo/extrator mudar?
