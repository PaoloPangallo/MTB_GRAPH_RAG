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

/**
 * Badge di modalità e origine.
 *
 * `CACHED DOCUMENT` è deliberatamente distinto da `REPLAY` e non ne è un
 * sinonimo: un documento letto dalla cache locale è parte di una run live,
 * mentre una risposta del modello registrata non lo è. Renderli con lo stesso
 * badge farebbe apparire come rigiocata una run che non lo è — e, cosa peggiore,
 * abituerebbe a leggere i due casi come equivalenti.
 *
 * Come per gli stati, l'etichetta testuale è l'unica fonte: il colore non porta
 * mai da solo l'informazione.
 */
export interface OriginBadge {
  label: string;
  fg: string;
  bg: string;
  tooltipKey: string;
}

export const originBadge: Record<string, OriginBadge> = {
  GENERATED_NOW: {
    label: 'LIVE', fg: '#0b5c3f', bg: '#e6f4ec', tooltipKey: 'live',
  },
  RECORDED_REAL_RUN: {
    label: 'REPLAY', fg: '#8a4b2f', bg: color.stone, tooltipKey: 'replayed',
  },
  DETERMINISTIC_CACHE: {
    label: 'CACHED DOCUMENT', fg: '#1863dc', bg: '#eef3fd', tooltipKey: 'cached_document',
  },
  NOT_APPLICABLE: {
    label: 'NOT IMPLEMENTED', fg: color.muted, bg: 'transparent', tooltipKey: 'deterministic',
  },
  NOT_EXECUTED: {
    label: 'SKIPPED', fg: color.muted, bg: 'transparent', tooltipKey: 'stopped',
  },
};

/** Badge di uno stage: FAILED prevale sull'origine, perché è ciò che conta. */
export function badgeFor(status: string, origin: string): OriginBadge {
  if (status === 'FAILED') {
    return { label: 'FAILED', fg: color.error, bg: '#fdf0f0', tooltipKey: 'stopped' };
  }
  return originBadge[origin] ?? originBadge.NOT_EXECUTED;
}

/**
 * Nome di presentazione dell'arresto terminale della catena documentale.
 *
 * Il reason code interno resta `LIVE_STAGE_FAILED` e simili: rinominarlo
 * toccherebbe contratti, artefatti storici e scorecard già prodotti, in cambio
 * di nulla. Ciò che cambia è come lo si chiama davanti a chi legge.
 */
export const PIPELINE_ABORT_LABEL = 'PIPELINE ABORT';

/** Etichette di run **storiche**. Il runtime canonico non ne usa nessuna. */
export const runModeStyle: Record<string, StatusStyle> = {
  LIVE: { label: 'LIVE', fg: '#0b5c3f', bg: '#e6f4ec', marker: 'filled' },
  REPLAY: { label: 'REPLAY', fg: '#8a4b2f', bg: color.stone, marker: 'barred' },
  HYBRID: { label: 'HYBRID', fg: '#8a4b2f', bg: '#fff3ee', marker: 'hollow' },
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
  // Esecuzione documentale reale.
  DOCUMENT_RESOLVED_FROM_CACHE: 'Documento risolto dalla cache autorizzata durante la run',
  DOCUMENT_UNAVAILABLE: 'Documento non presente nella cache: nessun artefatto è stato sostituito',
  DOCUMENT_NOT_IN_MANIFEST: 'Il documento non compare nel manifest',
  CACHE_MISS: 'Il manifest lo prevede ma il file non è nella cache',
  NO_LOCAL_CACHE_PATH: 'Il manifest non indica alcun file locale',
  NO_DOCUMENT_RESOLVED: 'Nessun documento risolto: la pipeline non prosegue su artefatti registrati',
  DOCUMENT_CACHE_UNAVAILABLE: 'Cache documentale non disponibile: la pipeline non ripiega sul replay',
  PARSER_FAILED: 'Nessuna Source Unit con testo utilizzabile: la pipeline si arresta',
  SOURCEUNIT_SELECTION_FAILED: 'Nessun passaggio rilevante selezionato: la pipeline si arresta',
  SOURCE_UNITS_MATERIALIZED_FROM_CACHE: 'Source Unit ricostruite dal documento durante la run',
  SOURCE_UNITS_FROM_RECORDED_INDEX: 'Locatori dall’indice congelato, senza testo ricostruito',
  SOURCE_UNIT_TEXT_UNAVAILABLE: 'Nessun testo disponibile per questa Source Unit',
  SOURCE_UNIT_PARSE_FAILED: 'Il documento non è stato interpretabile',
  DOCUMENT_FROM_RECORDED_RUN: 'Documento della run registrata: nessuna cache consultata',
  // Nome interno ereditato, conservato in contratti, artefatti e scorecard già
  // prodotti. Qui viene solo presentato con il nome che l'architettura gli dà.
  LIVE_STAGE_FAILED: 'Uno stage non è stato eseguito: nessun artefatto lo ha sostituito',
  NO_PAPER_SELECTED_FOR_ENRICHMENT: 'Nessun paper selezionato: il modello non è stato chiamato',
  MAX_PAPERS_PER_ASSOCIATION_EXCEEDED: 'Oltre il tetto di due paper per associazione',
  DUPLICATE_DOCUMENT_ID: 'Documento già selezionato per questa associazione',
  // Validazione v2.
  QUOTE_NOT_LITERAL_IN_SOURCE_UNIT: 'La citazione non compare letteralmente nella Source Unit',
  DRUG_NOT_PRESENT_IN_PASSAGE: 'Il farmaco richiesto non compare nel passaggio citato',
  SOURCE_UNIT_NOT_FOUND: 'La Source Unit indicata non esiste',
  SOURCE_UNIT_NOT_IN_PAPER: 'La Source Unit non appartiene al paper',
  SUMMARY_EMPTY: 'Riassunto vuoto: accettato, il protocollo lo consente',
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return 'non disponibile';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}
