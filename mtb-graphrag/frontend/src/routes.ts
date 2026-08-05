/**
 * Percorsi dell'applicazione.
 *
 * Sono costanti e non stringhe sparse perché la separazione fra le due pipeline
 * è la ragione stessa di questa struttura: un percorso scritto a mano nel punto
 * sbagliato riporterebbe la vista storica sul cammino principale senza che
 * nessun test se ne accorga.
 */

/** Pipeline verificabile: testo libero → parser → … → dossier. */
export const VERIFIABLE_PIPELINE_ROUTE = '/research/verifiable-pipeline';

/** Stessa vista, con la run nell'URL: un refresh non perde la trace. */
export const VERIFIABLE_PIPELINE_RUN_ROUTE = '/research/verifiable-pipeline/runs/:runId';

export function runRoute(runId: string): string {
  return `${VERIFIABLE_PIPELINE_ROUTE}/runs/${runId}`;
}

/** Vista storica V3. Raggiungibile, ma fuori dal percorso principale. */
export const LEGACY_V3_ROUTE = '/legacy/v3-deterministic';
