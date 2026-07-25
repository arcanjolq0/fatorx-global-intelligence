# Contrato de pacotes por país

## 1. Objetivo

Isolar conhecimento jurisdicional sem duplicar o domínio ou acoplar o núcleo a fontes específicas. Pacote não garante cobertura: fontes dependem de aprovação separada.

## 2. Estrutura proposta

```text
src/intelligence/country_packs/
├── contract/
├── registry/
├── us/
│   ├── manifest.yaml
│   ├── identifiers/
│   ├── normalization/
│   ├── terminology/
│   └── source_catalog_refs.yaml
├── gb/
└── de/
```

Diretórios serão criados somente na implementação.

## 3. Manifesto

Campos obrigatórios:

- `country_code` ISO alfa-2;
- `pack_version` SemVer;
- `contract_version`;
- `languages` BCP 47 ordenados por preferência;
- `legal_forms` e abreviações;
- `identifier_types`, formato, checksum quando oficial e escopo;
- `required_identity_fields` por tipo de entidade;
- formatos de endereço, data, número, moeda e unidade;
- categorias/capacidades suportáveis;
- códigos de termos jurídicos com traduções informativas;
- referências a `SourceDefinition` aprováveis, sem URL secreta ou credencial;
- compatibilidade mínima/máxima com o núcleo.

## 4. Portas do pacote

- validar e normalizar identificador, preservando original;
- normalizar nome/endereço sem apagar acentos ou versão original;
- classificar forma jurídica e tipo de registro;
- interpretar formatos locais de data/número/moeda;
- fornecer dicionário controlado de termos;
- declarar requisitos de identidade e regras de comparação específicas;
- mapear capacidades para referências de fonte aprovadas.

Pacote não executa rede, não persiste, não cria claim, não calcula risco e não contém prompt livre executável.

## 5. Regras de segurança e governança

- arquivos são dados de configuração validados por schema;
- nenhum segredo ou cookie;
- URL é apenas referência de catálogo submetida à política de fonte;
- mudança de semântica incompatível incrementa major;
- investigação registra a versão exata;
- pacote desativado não inicia novas investigações, mas continua disponível para reprodutibilidade histórica;
- termos traduzidos não substituem texto jurídico original.

## 6. Testes de contrato

- manifesto válido e compatível;
- código de país/idiomas/identificadores válidos;
- normalização idempotente e preservação do original;
- exemplos positivos, negativos e limites de checksum;
- nomes com diacríticos e transliteração sem colisão silenciosa;
- datas/números/moedas locais;
- ausência de rede, segredos e imports de infraestrutura;
- referências de fonte inexistentes falham no carregamento;
- mesmo input/versão produz mesma saída.

## 7. Ordem de entrega

Estados Unidos, Reino Unido e Alemanha permanecem candidatos do plano. A ordem real depende de volume comercial e fontes aprovadas. Implementar e aceitar um pacote por vez; um skeleton de pacote sem cobertura não pode ser divulgado como país suportado.

## 8. Critério para “país suportado”

Um país só pode ser marcado como suportado quando:

1. pacote e testes estão aprovados;
2. matriz de capacidades do perfil comercial possui fontes reais aprovadas;
3. identidade e falso positivo foram validados com corpus representativo autorizado;
4. limitações, idioma, retenção e termos aparecem no produto;
5. operação, custo e SLA foram aceitos.
