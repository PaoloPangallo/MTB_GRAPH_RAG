/** Unico runtime operativo della pipeline della tesi. */
export const VERIFIABLE_PIPELINE_ROUTE = '/research/verifiable-pipeline';
export const VERIFIABLE_PIPELINE_RUN_ROUTE = '/research/verifiable-pipeline/runs/:runId';
export const ARCHITECTURE_ROUTE = '/architecture';
export function runRoute(runId: string): string {
  return `${VERIFIABLE_PIPELINE_ROUTE}/runs/${encodeURIComponent(runId)}`;
}
