# ADR-0005 — Pacotes versionados por país

- Status: Accepted
- Data: 2026-07-25

## Contexto

Identificadores, formas jurídicas, formatos, idiomas e fontes variam por jurisdição. Condicionais espalhados pelo núcleo tornariam a expansão arriscada.

## Decisão

Criar contrato de pacote por ISO alfa-2 e versão. Pacotes fornecem dados/normalizadores/terminologia e referências ao catálogo de fontes. Não executam rede, não persistem, não calculam risco, não contêm credenciais e não duplicam o domínio.

## Consequências

- Uma investigação registra versão para reprodutibilidade.
- País só é divulgado como suportado após pacote e cobertura aprovados.
- Mudança incompatível incrementa versão major.
- Estados Unidos, Reino Unido e Alemanha são candidatos, não acessos presumidos.
