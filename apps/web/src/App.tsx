export function App() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Ir para o conteúdo principal
      </a>

      <header className="site-header" aria-label="Cabeçalho da aplicação">
        <span className="product-name">Fator X</span>
        <span className="phase-label">
          <span className="phase-dot" aria-hidden="true" />
          Fase inicial
        </span>
      </header>

      <main id="main-content" className="main-content" tabIndex={-1}>
        <section className="intro" aria-labelledby="page-title">
          <p className="eyebrow">Fundação técnica</p>
          <h1 id="page-title">Fator X Global Intelligence</h1>
          <p className="lead">
            Plataforma de investigação empresarial internacional orientada por evidências.
          </p>

          <div className="status-panel" role="status" aria-label="Estado atual do sistema">
            <span className="status-title">Ambiente inicial</span>
            <p>
              A fundação executável está pronta. Os recursos de investigação ainda não foram
              habilitados.
            </p>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <span>Fase 1</span>
        <span aria-hidden="true">·</span>
        <span>Sem integrações externas</span>
      </footer>
    </div>
  );
}
