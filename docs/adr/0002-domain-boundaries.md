# ADR-0002 — Conectores não controlam domínio nem projeções

- Status: Accepted
- Data: 2026-07-25

## Contexto

O contrato de entrada sugeria que conectores avaliassem correspondência e criassem evidência. Isso repetiria regras por fornecedor e acoplaria integração a identidade/persistência.

## Decisão

Conectores retornam candidatos, observações e artefatos por envelope tipado. Resolução de entidades, admissibilidade, evidência canônica, claims, scoring e relatórios pertencem a módulos centrais. O domínio não importa SDK, HTTP, banco, fila ou framework web.

## Consequências

- Troca de fonte não altera regra de negócio.
- Há uma etapa explícita de transformação entre observação e evidência.
- O envelope precisa suportar localização e proveniência suficientes.
- Testes de arquitetura e contrato impedem imports/escritas proibidos.
