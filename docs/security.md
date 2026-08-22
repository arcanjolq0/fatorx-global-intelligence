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

Na F2.4.2, `ActorContext` representa uma identidade já autenticada por camada futura, sem token ou sessão. O autorizador exige usuário e membership ativos no workspace do contexto e permissão fechada para o papel. Serviços nunca aceitam outro workspace; repositórios não autorizam nem auditam por efeito colateral. Em produção futura, somente a fronteira de autenticação poderá construir o contexto confiável.

ADMIN administra somente ANALYST/VIEWER e nunca a própria membership. OWNER pode administrar owners, inclusive a si mesmo, somente quando outro owner ativo permanece. A retirada de owner bloqueia todas as linhas de owners ativos em ordem determinística, evitando a corrida de duas aprovações simultâneas.

## 4. Segredos

- cofre/variáveis de ambiente com referências, nunca valores em código;
- `.env.example` contém nomes e placeholders vazios;
- rotação e revogação por fonte;
- credencial de produção indisponível em CI/teste;
- redaction de headers, query strings e exceções;
- scanner de segredos no commit e pipeline.

Na F3.1, o descritor guarda somente um nome canônico de referência. O contexto
aceita um handle opaco por `Protocol`, excluído de `repr`, igualdade e hash.
Payloads ocultam bytes, paginação redige cursor e mensagens públicas rejeitam
marcadores comuns de segredo, URL e quebras de linha. Nenhum valor de credencial
é permitido nos envelopes ou fixtures.

## 5. Coleta e SSRF

Na F3.1 não existe coleta, URL de destino, DNS, redirecionamento, socket ou
cliente HTTP. Os contratos aceitam somente domínio canônico na query e
referências lógicas/opacas para origem e artefato; não oferecem método de busca.
As proteções runtime abaixo continuam obrigatórias para uma futura integração,
mas não são antecipadas pelo registro tipado.

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

Os códigos de ação e razão da F2.4.2 são enums fechados; eventos não aceitam payload arbitrário. Sucesso de mutação e mudança compartilham commit. Negação persiste evento sem mutação e só depois retorna erro constante. Recurso de outro workspace aparece como ausente e seu ID não é copiado para o evento negado. Leituras bem-sucedidas não são auditadas nesta fase para evitar retenção prematura de alto volume.

Na F4.1, o snapshot de identificação é dado empresarial potencialmente
sensível. Ele não entra em `repr` público de comando/agregado, erro, log ou
`AuditEvent`. O evento de sucesso contém somente ator, workspace, investigação,
ação fechada, outcome, razão fechada quando aplicável, correlação e instante.
O digest do comando é construído por allowlist canônica e não substitui o
controle de acesso ao snapshot. Replay e lookup usam tenant antes do ID, e a FK
composta do ledger impede associação entre investigação e workspace distintos.

O JSONB aceita somente o schema fechado de nomes, identificadores, domínio,
endereço e idioma. Documento, token, cookie, segredo, URL arbitrária e payload
externo não fazem parte do contrato. Conteúdo original é preservado somente nos
campos previstos, enquanto normalização permanece derivado separado.

Na F4.2, identidade e origem de candidatos são igualmente envelopes fechados e
versionados. Limites de quantidade/tamanho e vocabulários são validados antes de
matching/persistência. O matcher não usa rede, arquivo, ambiente, subprocesso,
relógio ou aleatoriedade. Auditoria registra somente command ID, política/versão,
quantidade e classificação de topo; não registra nomes, identificadores,
endereços, administradores, score dimensional, snapshot ou SQL. Candidato é
dado não confiável e nunca é promovido automaticamente a fato ou empresa.

Na F4.3, o comando aceita apenas IDs tipados, motivo fechado e política canônica;
não aceita texto livre, URL, payload, Company ID ou candidato inline. Auditoria
registra somente IDs, motivo, rank/classificação e IDs/versões das políticas.
Nome, identificadores, domínio, origem e snapshots permanecem fora de audit e
`repr`. Todas as leituras são tenant-first e a decisão é reconstituída com
Investigation, lote, candidato e Company. `EXCLUDED` é bloqueado mesmo sob
override. Candidato e decisão continuam dados não confiáveis, não evidência.

Na F4.4, o cliente fornece somente comando, Investigation, versão esperada e a
política fechada suportada; não fornece conectores, plano, custo ou destino. O
serviço autoriza antes de carregar recursos, usa locks tenant-scoped e lê Company
e Investigation pelo workspace do ator. O planner consome cópias de descritores
capturadas na admissão, sem rede, credenciais, ambiente ou disponibilidade
externa. A auditoria allowlisted contém apenas IDs, contagens, política e custo
agregado tipado; nomes, identificadores, domínios, payloads e credenciais ficam
de fora.

Na F4.4.1, o check de auditoria exige ausência total dos quatro campos de
comando/custo ou um conjunto tipado completo. A continuidade histórica ainda
valida Company tenant-scoped, lote ativo nulo e versão monotônica; ela não amplia
autorização nem executa recursos externos.

Na F4.5, o cliente informa somente comando, Investigation, plano, versão
esperada e política fechada. Conector escolhido, operações, IDs internos,
status, custo e destino são derivados do plano persistido. FKs compostas e
unicidades protegem run/operações/dependências por tenant; digests são
recalculados na leitura. A auditoria contém apenas IDs, contagem, política,
custo agregado tipado, resultado e correlação. Nenhum snapshot, nome, domínio,
payload ou credencial é auditado. A ativação não acessa rede ou segredo.

Na F4.5.1, a revalidação de prazo acontece antes de IDs e materialização. A
leitura fail-closed exige a transição histórica exata e usa os vínculos compostos
de workspace, Investigation, Company e plano como defesa em profundidade. Erro
de integridade não é convertido em replay ou ausência tenant-scoped.

Na F4.6, o comando não escolhe conector: a composição fornece uma implementação
explicitamente allowlisted, `TEST` e idêntica ao snapshot do manifesto. O ownership
durável precede o I/O. Source policy, locales e política de execução ficam
preservados no ownership; a conclusão exclui nomes, domínios, itens, observações,
artefatos, payloads e credenciais. Fonte real e rede permanecem bloqueadas, e
ownership sem conclusão falha fechado como execução em andamento.

A FK obrigatória de `audit_event.actor_user_id` impede registrar `ACTOR_USER_NOT_FOUND`: o ator inexistente não pode ser referenciado sem violar o schema aprovado. Nesse único caso, a tentativa de auditoria falha, a negação original é preservada e nenhum detalhe técnico é exposto. Corrigir essa limitação exigiria decisão de schema própria; a F2.4.2 não cria migration silenciosa.

- hash de artefato/evidência;
- versões imutáveis de políticas, métodos e regras;
- repositórios vinculados à identidade da transação original; commit/rollback encerram imediatamente sua capacidade de operar, ainda que a conexão permaneça aberta;
- guard invalidado antes da finalização; falha de commit/rollback não permite reutilizar uma transação de resultado incerto, mesmo quando o driver ainda a apresenta como ativa;
- eventos para acesso, exportação, revisão e transição;
- `AuditEvent` persistido é imutável no domínio e seu repositório aceita somente append; não há cascata destrutiva, JSON genérico ou expurgo nesta fase;
- horário confiável e correlação ponta a ponta;
- logs append-only/protegidos conforme operação;
- nunca registrar conteúdo completo por conveniência.

Na F5.1, comandos e registros ocultam bytes/trechos em `repr`; auditoria contém
somente ator, workspace, Investigation, ação, resultado e correlação. Digests de
comando usam hashes, não payload. FKs compostas ligam evidência a artefato,
Investigation, Company e decisão no mesmo tenant. Conteúdo original integral não
é escrito no PostgreSQL; somente trecho explicitamente permitido pode ser
persistido. A história completa é validada antes de qualquer append; colisão,
contexto inválido, versão obsoleta, revogação repetida e leitura ausente geram
auditoria redigida sem copiar o ID potencialmente pertencente a outro tenant.
Discriminadores de locator e escapes RFC 6901 falham na fronteira. Não há
endpoint, upload, URL fetch ou object storage nesta subfase.

Na F5.2 aceita, confiança não deriva de `source_id`, `origin_type`, IDs runtime
ou hash do Artifact isolado. O manifesto interno exige âncora exata de Artifact,
conteúdo, kind e locator canônico; duplicidade e adulteração falham fechado.
Comandos não contêm outcome, reason, policy ou manifesto. FKs compostas e
consultas tenant-scoped protegem contra IDOR/cross-tenant; digests são
recalculados na reconstituição. Locks de Evidence serializam registro/correção
de Claim contra correção e revogação, evitando decisão baseada em versão que
mudou; o assessment também adquire todos os locks antes da releitura. Snapshots
JSON exigem chaves, tipos e forma canônica exatos, e a proveniência de cada
decisão é vinculada à versão da Claim. Auditoria e `repr` excluem ClaimValue,
conteúdo, locator, origem e hashes. Não há SQL textual derivado de input, rede,
filesystem, JSON aberto, segredo, HTTP ou mecanismo F5.3 nesta fronteira.

Na implementação candidata F5.3, confiança positiva exige match exato no manifesto
F5.3 próprio; rótulos como `source_id`, filename, método ou `origin_type` não concedem
trust e a raiz F5.2 não é suficiente. `ADMIT` bloqueia self-approval da versão exata.
Locks e revalidação impedem aprovação stale, após supersession ou revogação. A FK
composta impede desacoplamento ID/série/versão/contexto. Audit não contém conteúdo,
locator, hashes ou digest do manifesto, e downgrade recusa apagar história existente.

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
