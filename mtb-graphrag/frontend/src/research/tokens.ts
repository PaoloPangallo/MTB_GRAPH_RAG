/**
 * Token visivi della console di ricerca, derivati dal design system fornito.
 *
 * Il criterio con cui la palette è stata mappata su questo dominio: il colore
 * arriva dal **contenuto**, non dalla decorazione. Nel design system il coral è
 * riservato alle chip di tassonomia; qui la tassonomia che conta è *chi ha
 * prodotto un risultato*, quindi il coral marca i due soli stage prodotti da un
 * modello e nient'altro. Tutto il resto della shell resta monocromatico.
 */

export const color = {
  /** Canvas dominante. */
  canvas: '#ffffff',
  /** Barra di marcatura e testo ad alto contrasto. */
  black: '#000000',
  ink: '#17171c',
  body: '#212121',
  /** Superficie calda: artefatti congelati, cioè materiale d'archivio. */
  stone: '#eeece7',
  /** Banda scura per il dossier: è l'esito, e merita un fondo proprio. */
  deepGreen: '#003c33',
  /** Tassonomia del producer: solo stage LLM. */
  coral: '#ff7759',
  coralSoft: '#ffad9b',
  /** Link a fonti e identificatori risolvibili. */
  actionBlue: '#1863dc',
  /** Metadati, etichette secondarie. */
  slate: '#75758a',
  muted: '#93939f',
  hairline: '#d9d9dd',
  borderLight: '#e5e7eb',
  /** Errore. Usato con parsimonia: quasi nulla qui è un errore. */
  error: '#b30000',
  focus: '#4c6ee6',
} as const;

export const font = {
  display: '"Space Grotesk", "Inter", ui-sans-serif, system-ui, sans-serif',
  body: '"Inter", Arial, ui-sans-serif, system-ui, sans-serif',
  mono: '"IBM Plex Mono", "SFMono-Regular", Consolas, monospace',
} as const;

export const radius = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 22,
  pill: 32,
} as const;

/**
 * Resa di uno stato di stage.
 *
 * `label` non è ridondante rispetto al colore: l'accessibilità richiede che lo
 * stato non sia indicato dal solo colore, e questa è la sua unica fonte.
 * `marker` distingue pieno da cavo, così lo stato resta leggibile anche in
 * scala di grigi.
 */
export interface StatusStyle {
  label: string;
  fg: string;
  bg: string;
  marker: 'filled' | 'hollow' | 'barred';
}

export const stageStatusStyle: Record<string, StatusStyle> = {
  SUCCEEDED: { label: 'Completato', fg: color.ink, bg: 'transparent', marker: 'filled' },
  WARNING: { label: 'Con riserva', fg: '#8a4b2f', bg: '#fff3ee', marker: 'filled' },
  FAILED: { label: 'Fallito', fg: color.error, bg: '#fdf0f0', marker: 'barred' },
  SKIPPED: { label: 'Non eseguito', fg: color.muted, bg: 'transparent', marker: 'hollow' },
  RUNNING: { label: 'In corso', fg: color.actionBlue, bg: '#f1f5ff', marker: 'hollow' },
  PENDING: { label: 'In attesa', fg: color.muted, bg: 'transparent', marker: 'hollow' },
};

export const runStatusStyle: Record<string, StatusStyle> = {
  COMPLETED: { label: 'Completata', fg: color.deepGreen, bg: '#edfce9', marker: 'filled' },
  PARTIAL: { label: 'Completata con riserve', fg: '#8a4b2f', bg: '#fff3ee', marker: 'filled' },
  // Un arresto corretto non è un guasto: non va colorato di rosso.
  STOPPED: { label: 'Fermata correttamente', fg: color.ink, bg: color.stone, marker: 'barred' },
  FAILED: { label: 'Fallita', fg: color.error, bg: '#fdf0f0', marker: 'barred' },
  RUNNING: { label: 'In corso', fg: color.actionBlue, bg: '#f1f5ff', marker: 'hollow' },
  CREATED: { label: 'Creata', fg: color.muted, bg: 'transparent', marker: 'hollow' },
};

/** Traduzioni dei reason code che il relatore leggerà più spesso. */
export const REASON_LABELS: Record<string, string> = {
  CASECONTEXT_MISMATCH: 'Un campo essenziale non trova riscontro nel testo clinico',
  RETRIEVAL_NO_MATCH: 'Il grafo non propone candidate compatibili con il caso',
  PARSER_TRANSPORT_FAILED: 'Il modello non ha restituito una chiamata a tool valida',
  CALL_BUDGET_EXCEEDED: 'Budget di chiamate al modello esaurito',
  NOT_IMPLEMENTED: 'Stage previsto dal contratto ma non implementato',
  TEXT_NOT_AVAILABLE_IN_CACHE: 'Nessuna Source Unit con testo disponibile per questo documento',
  NO_VALIDATED_ENRICHMENT_AVAILABLE: 'Nessuna citazione validata: nessun segnale documentale',
  SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING: 'Almeno una citazione accettata con riserva',
  VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION:
    'La citazione validata non parla della direzione dell’effetto',
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return 'non disponibile';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}
