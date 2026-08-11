# ADR-0018 — Integridade da avaliação persistida de matching

- Status: `Accepted`
- Data: 2026-08-01
- Decisão anterior relacionada: ADR-0017

## Contexto

A F4.2 persistiu snapshots e digests suficientes para explicar o matching, mas
a reconstituição não os reunia em uma avaliação oficial. Validar apenas formato
hexadecimal, faixas e alguns vínculos aceitaria corrupção manual semanticamente
incompatível. Também não era possível recalcular o digest da submissão quando a
ordem recebida diferia do ranking, pois a ordem original não existe no schema.

## Decisão

Reconstituir fail-closed o grafo canônico inteiro no limite
aplicação/persistência:

1. reconstruir e validar o `MatchPolicy` persistido;
2. reconstruir identidade, origem e `EntityCandidateInput`;
3. reconstruir cada `DimensionScore` e validar seu peso contra a política;
4. reconstruir cada `CandidateEvaluation` com candidate, input e policy digest;
5. reconstruir o `CandidateSubmissionBatch` e seu digest;
6. reaplicar a única função oficial de ranking;
7. reconstruir `CandidateBatchEvaluation` e comparar o digest agregado.

O contexto obrigatório de política e input passa a integrar o record de
candidato em memória, embora continue persistido somente no cabeçalho do lote.
Assim não existe validação opcional que o mapper possa esquecer.

A representação canônica do `CandidateSubmissionBatch` ordena candidatos por
`candidate_key`. A tupla recebida não é mutada, o matcher e o ranking não mudam,
mas o digest passa a representar o conjunto tipado, não a ordem incidental de
submissão. Isso permite reconstrução sem coluna ou migration nova.

O schema 1 reconhece exclusivamente `NAME_NORMALIZATION_V1`. Não existe seleção
dinâmica fictícia de normalizador.

## Consequências

- qualquer diferença em score, peso, contribuição, explicação, cobertura,
  classificação, conflito, contexto, digest ou ranking interrompe a leitura;
- mensagens da persistência permanecem fixas e sem payload;
- permutações de entrada do mesmo conjunto passam a ter o mesmo submission e
  command digest, coerentes com resultado de matching idêntico;
- lote preliminar persistido com digest dependente de ordem não canônica pode
  exigir saneamento ou reenvio;
- a migration `20260729_04`, tabelas, pesos, thresholds e lifecycle não mudam.

## Alternativas rejeitadas

- confiar no formato SHA-256: não prova correspondência com conteúdo;
- duplicar cálculo no mapper: criaria risco de divergência do matcher;
- testar permutações até encontrar o digest: não é limitado nem seguro para 100
  candidatos;
- inferir ordem por UUID ou ordem física: não é contrato relacional;
- criar coluna de ordem e backfill: a ordem histórica não pode ser recuperada
  de modo confiável e não é semântica do matching.

## Limites

A validação prova consistência interna, não autenticidade externa do dado. Não
há assinatura criptográfica, conector, evidência, claim, decisão humana ou
empresa canônica. F4.3 e o gate da Fase 4 continuam não autorizados.
