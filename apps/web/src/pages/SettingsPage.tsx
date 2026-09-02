import { Badge, Card } from "../components/ui";

const visualPreferences = [
  { label: "Tema", value: "Claro" },
  { label: "Densidade", value: "Equilibrada" },
  { label: "Idioma", value: "Português (Brasil)" },
] as const;

const unavailableCapabilities = [
  {
    title: "Persistência de preferências",
    description: "As escolhas visuais ainda não são gravadas entre sessões.",
  },
  {
    title: "Autenticação e permissões",
    description:
      "Não há sessão autenticada, perfis de acesso ou gestão de usuários nesta interface.",
  },
  {
    title: "Integrações e fontes reais",
    description: "Nenhuma fonte externa, credencial ou catálogo produtivo está conectado.",
  },
  {
    title: "Exportação e notificações",
    description: "Relatórios produtivos, downloads e alertas permanecem indisponíveis.",
  },
] as const;

export function SettingsPage() {
  return (
    <div className="page-stack settings-page">
      <section aria-labelledby="settings-title" className="page-intro">
        <div>
          <p className="eyebrow">Ambiente de demonstração</p>
          <h2 id="settings-title">Preferências e limites do workspace</h2>
          <p>
            Consulte a configuração visual ativa e as fronteiras desta sessão sem sugerir recursos
            produtivos ainda inexistentes.
          </p>
        </div>
        <Badge tone="neutral">Somente leitura</Badge>
      </section>

      <p className="semantic-boundary-banner semantic-boundary-banner--strong">
        <strong>Nenhuma alteração é salva.</strong>
        Esta tela descreve o estado local da demonstração. Não há API de preferências, autenticação
        ou persistência conectada.
      </p>

      <div className="settings-grid">
        <Card title="Workspace">
          <dl className="settings-definition-list">
            <div>
              <dt>Nome</dt>
              <dd>Fator X Global Intelligence</dd>
            </div>
            <div>
              <dt>Experiência</dt>
              <dd>Workspace investigativo</dd>
            </div>
            <div>
              <dt>Modo</dt>
              <dd>
                <Badge tone="info">Demonstração local</Badge>
              </dd>
            </div>
            <div>
              <dt>Conectividade</dt>
              <dd>Sem API ou serviço externo</dd>
            </div>
          </dl>
        </Card>

        <Card title="Preferências visuais">
          <ul className="preference-list">
            {visualPreferences.map((preference) => (
              <li key={preference.label}>
                <span>{preference.label}</span>
                <strong>{preference.value}</strong>
              </li>
            ))}
          </ul>
          <p className="card__summary">
            Valores fixos nesta prévia. Controles editáveis só serão exibidos quando houver uma
            fronteira real para salvar preferências.
          </p>
        </Card>

        <Card title="Dados da sessão de demonstração">
          <dl className="settings-definition-list">
            <div>
              <dt>Origem</dt>
              <dd>Fixtures sintéticas tipadas</dd>
            </div>
            <div>
              <dt>Cenário</dt>
              <dd>Populado e determinístico</dd>
            </div>
            <div>
              <dt>Armazenamento</dt>
              <dd>Somente estado temporário no navegador</dd>
            </div>
            <div>
              <dt>Uso externo</dt>
              <dd>Nenhum dado é enviado</dd>
            </div>
          </dl>
        </Card>

        <Card title="Leitura responsável">
          <ul className="scope-list">
            <li>Os nomes, IDs e eventos exibidos pertencem ao cenário sintético.</li>
            <li>Estados F5.2, F5.3 e F5.4 mantêm finalidades independentes.</li>
            <li>Não há score, decisão de crédito ou conclusão factual automática.</li>
          </ul>
        </Card>
      </div>

      <Card className="capabilities-card" title="Capacidades indisponíveis">
        <ul className="capability-list">
          {unavailableCapabilities.map((capability) => (
            <li key={capability.title}>
              <span>
                <strong>{capability.title}</strong>
                <small>{capability.description}</small>
              </span>
              <Badge tone="neutral">Indisponível</Badge>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
