# Segurança e privacidade

## 1. Objetivo

Proteger usuários, empresas investigadas, documentos, credenciais, fontes licenciadas e integridade das conclusões. Todo conteúdo externo é não confiável.

## 2. Fronteiras de confiança

- navegador do usuário -> web/API;
- API -> casos de uso e banco;
- orquestrador/worker -> fila;
- worker -> internet/fonte externa;
- upload -> quarentena/parsing;
- aplicação -> provedor de modelo;
- aplicação -> storage de objetos;
- aplicação -> exportação/CRM futuro.

Dados devem ser validados em cada fronteira; estar em rede interna não os torna confiáveis.

## 3. Identidade e autorização

- autenticação delegada a provedor aprovado; nenhuma senha própria no MVP;
- workspace obrigatório e papéis de menor privilégio;
- autorização no caso de uso, não somente na UI;
- acesso a artefato via autorização e URL curta/assinada quando aplicável;
- exportação e revisão crítica exigem permissão e auditoria;
- contas de serviço separadas por componente/ambiente;
- sessões, revogação e MFA dependem da política organizacional a validar.

Na F2.3, filtros compostos por `workspace_id` nos repositórios de empresa e investigação reforçam o isolamento relacional, mas não autenticam um ator nem comprovam membership. A F2.4 implementará o isolamento no nível dos serviços, memberships e auditoria mínima como fronteira própria. Repositórios não autorizam operações nem registram auditoria por efeito colateral.

## 4. Segredos

- cofre/variáveis de ambiente com referências, nunca valores em código;
- `.env.example` contém nomes e placeholders vazios;
- rotação e revogação por fonte;
- credencial de produção indisponível em CI/teste;
- redaction de headers, query strings e exceções;
- scanner de segredos no commit e pipeline.

## 5. Coleta e SSRF

- conectores usam destinos aprovados, não URL arbitrária do usuário;
- HTTPS obrigatório salvo exceção formal;
- resolver DNS e bloquear loopback, privado, link-local, multicast e metadata endpoints;
- validar cada redirect e impedir mudança para esquema/host proibido;
- limite de redirects, tamanho, tempo, bytes e tipo;
- proteção contra DNS rebinding e interpretação ambígua de IP;
- egress de browser/worker limitado por política;
- não contornar autenticação, paywall, CAPTCHA, rate limit ou bloqueio.

## 6. Conteúdo externo e prompt injection

- páginas, documentos, emails, JSON e texto OCR são dados delimitados;
- instruções contidas neles são ignoradas;
- modelo não escolhe ferramenta/destino/credencial com base em conteúdo;
- ferramentas possuem allowlist e argumentos validados pela aplicação;
- contexto enviado é minimizado e rotulado por proveniência;
- saída de modelo obedece schema, é sanitizada e não altera risk/state diretamente;
- claims críticos exigem evidência e revisão independentemente do modelo.

## 7. Uploads e documentos

- limite de bytes, páginas, descompressão e tempo;
- nome do arquivo não determina tipo; validar magic bytes e estrutura;
- quarentena antes de análise e verificação por mecanismo aprovado;
- não executar macros, scripts, objetos embutidos, links ou fontes remotas;
- parser/OCR em processo/container isolado com CPU/memória/tempo limitados;
- armazenar original criptografado somente conforme política;
- downloads e previews com headers seguros e sanitização.

## 8. Dados e privacidade

- minimização por finalidade;
- classificação: público, licenciado, confidencial, pessoal e sensível;
- base legal e retenção por classe/jurisdição;
- separação lógica por workspace em banco, cache, fila e storage;
- criptografia em trânsito; em repouso conforme serviço/política;
- contatos pessoais apenas quando necessários e permitidos;
- expurgo auditável, incluindo derivados e índices;
- ambientes não produtivos usam dados sintéticos/redigidos.

## 9. Integridade e auditoria

- hash de artefato/evidência;
- versões imutáveis de políticas, métodos e regras;
- eventos para acesso, exportação, revisão e transição;
- horário confiável e correlação ponta a ponta;
- logs append-only/protegidos conforme operação;
- nunca registrar conteúdo completo por conveniência.

## 10. API e web

- validação estrita de payload e limites;
- proteção contra acesso horizontal/vertical;
- CSRF quando a forma de autenticação exigir;
- CORS mínimo por ambiente;
- rate limit por ator/workspace;
- output encoding, HTML sanitizado e CSP planejada;
- erros públicos sem stack, segredo ou payload.

## 11. Supply chain

- lockfiles e builds reproduzíveis;
- dependência justificada e com licença avaliada;
- scanner de vulnerabilidades e atualização planejada;
- imagens mínimas, fixadas por digest quando validadas, e identidade não root quando aplicável;
- artefatos de build assináveis/provenientes conforme maturidade;
- nenhum script remoto executado sem pin/revisão.

### 11.1 Banco destrutivo de teste

Testes que executam downgrade não confiam apenas em convenções de nome. Eles exigem consentimento pontual `FATORX_ALLOW_DESTRUCTIVE_DATABASE_TESTS=1`, host de loopback em allowlist e nome dedicado no padrão `fatorx_test` ou `fatorx_test_<sufixo seguro>`. Query string e variáveis libpq capazes de alterar o alvo são rejeitadas. `PGOPTIONS` também é bloqueada porque pode mudar o `search_path` e redirecionar DDL para outro schema sem alterar host ou banco. A validação precede engine, conexão e Alembic; qualquer falha retorna mensagem fixa sem URL ou credenciais. O consentimento não fica ativo em `.env.example` e nunca autoriza execução contra ambiente compartilhado.

## 12. Modelo de ameaças prioritário

| Ameaça | Controle principal |
|---|---|
| falso match que prejudica empresa | entidade por múltiplos sinais + revisão |
| adulteração de evidência | hash, original, locator e append-only |
| exfiltração por prompt injection | ferramentas restritas + conteúdo como dado |
| SSRF para rede interna | allowlist/validação DNS/redirect/egress |
| malware em documento | quarentena, scan e sandbox |
| vazamento de licença/PII | policy, tenancy, acesso e retenção |
| segredo em log | allowlist/redaction/scanner |
| alteração silenciosa de score | versões imutáveis, digest e auditoria |
| duplicação por retry | idempotência e inbox/outbox |

## 13. Resposta e operação

- playbooks para segredo exposto, fonte comprometida, vazamento, falso positivo crítico e adulteração;
- feature flag/kill switch por conector e país;
- preservação de evidência de incidente com acesso restrito;
- notificação e prazos conforme política/jurisdição;
- testes periódicos de restauração e revogação.

## 14. Gates

Antes de piloto: threat model revisado, testes de segurança passando, achados críticos/altos resolvidos ou formalmente aceitos, retenção/base legal aprovadas e owners de incidente nomeados.
