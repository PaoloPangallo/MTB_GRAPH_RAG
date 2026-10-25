/**
 * Token visivi della console di ricerca, derivati dal design system fornito.
 *
 * Il criterio con cui la palette è stata mappata su questo dominio: il colore
 * arriva dal **contenuto**, non dalla decorazione. Nel design system il coral è
 * riservato alle chip di tassonomia; qui la tassonomia che conta è *chi ha
 * prodotto un risultato*, quindi il coral marca gli stage dichiarati prodotti da un
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
  slate: '#595968',
  muted: '#626270',
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
  lg: 16,
  pill: 32,
} as const;

/** Sticky view tabs plus clearance for anchored headings and side navigation. */
export const workspaceOffset = 80;

/** Source identity is independent from execution status and clinical support. */
export const sourceStyle = {
  paper: { fg: '#2455a0', bg: '#eef4fc', label: 'Pubblicazioni' },
  trial: { fg: '#00685e', bg: '#edf7f4', label: 'Studi clinici' },
  kg: { fg: '#684295', bg: '#f5f0fa', label: 'Knowledge Graph' },
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
  MOLECULAR_PHENOTYPE_SCOPE_UNSPECIFIED: 'Il risultato molecolare richiede un chiarimento sul grado riportato',
  MOLECULAR_PHENOTYPE_DOMAIN_UNSUPPORTED: 'Il fenotipo è conservato; la sua identità richiede una verifica dedicata',
  SEMANTIC_OUTPUT_SCHEMA_INVALID: 'Valutazione semantica incompleta o incompatibile con il contratto corrente',
  SEMANTIC_REQUIRED_SPAN_MISSING: 'Manca un passaggio letterale richiesto per il confronto',
  SEMANTIC_CONTEXT_MISSING: 'Contesto documentale autorizzato non disponibile',
  SEMANTIC_EVIDENCE_ROLE_STUDY_DESIGN: 'Il passaggio descrive lo studio, senza dimostrare un risultato',
  SEMANTIC_EVIDENCE_ROLE_ELIGIBILITY: 'I criteri di inclusione non dimostrano un risultato terapeutico',
  SEMANTIC_EVIDENCE_ROLE_BACKGROUND: 'Informazione di contesto, senza risultato diretto della relazione',
  SEMANTIC_MOLECULAR_SCOPE_NARROWER: 'Il risultato riguarda un sottotipo molecolare più specifico',
  SEMANTIC_POPULATION_SCOPE_NARROWER: 'Il risultato riguarda una popolazione più specifica',
  SEMANTIC_INTERVENTION_SCOPE_COMBINATION: 'Il risultato sul regime non dimostra quello del singolo intervento',
  SEMANTIC_INFERENCE_INVERSE: 'La relazione richiederebbe un’inferenza inversa non dimostrata',
  SEMANTIC_INFERENCE_INDIRECT: 'Il passaggio non esprime direttamente la relazione candidata',
  SEMANTIC_CERTAINTY_UNCERTAIN: 'La fonte mantiene un’incertezza sulla relazione',
  SEMANTIC_CERTAINTY_UNKNOWN: 'La certezza della relazione non è determinabile',
  CASECONTEXT_MISMATCH: 'Un campo essenziale non trova riscontro nel testo clinico',
  RETRIEVAL_NO_MATCH: 'Il grafo non propone candidate compatibili con il caso',
  PARSER_TRANSPORT_FAILED: 'Il modello non ha restituito una chiamata a tool valida',
  PROVIDER_RATE_LIMITED: 'Il provider ha limitato le chiamate al modello. Riprova dopo il ripristino della disponibilità.',
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
  NARRATIVE_ABSENT: 'La spiegazione narrativa non è disponibile',
  FORCED_TOOL_IGNORED: 'Il modello non ha restituito il risultato nel formato richiesto',
  DISEASE_CONTEXT_SCOPE_UNRESOLVED: 'La patologia coincide, ma il contesto clinico della citazione resta da verificare',
  SAME_CONCEPT_CONTEXT_UNRESOLVED: 'Stessa patologia; equivalenza delle qualificazioni cliniche non verificata',
  NARRATIVE_STATUS_ESCALATION: 'La spiegazione non rispetta lo stato canonico',
  NARRATIVE_OBSERVATION_CHECK_MISMATCH: 'La spiegazione non rispetta i controlli registrati per l’osservazione',
  NARRATIVE_OBSERVATION_VARIANT_ESCALATION: 'La spiegazione attribuisce alla singola variante un risultato non dimostrato',
  NARRATIVE_OBSERVATION_CAUSAL_ESCALATION: 'La spiegazione attribuisce un effetto causale non dimostrato dall’osservazione',
  NARRATIVE_PATIENT_ELIGIBILITY_UNASSESSED: 'La spiegazione presume un’idoneità del paziente che non è stata valutata',
  NARRATIVE_OBSERVATION_REGIMEN_UNPROVEN: 'La spiegazione attribuisce un risultato a un regime terapeutico non dimostrato',
  NARRATIVE_OBSERVATION_PHENOTYPE_SCOPE_OMITTED: 'La spiegazione omette i limiti della popolazione associata al fenotipo',
  NARRATIVE_UNAUTHORIZED_ENTITY: "La spiegazione contiene un'entità non autorizzata",
  NARRATIVE_UNAUTHORIZED_QUOTE: 'La spiegazione contiene una citazione non autorizzata',
  NARRATIVE_RECOMMENDATION_LANGUAGE: 'La spiegazione contiene linguaggio prescrittivo',
  NARRATIVE_VERIFIER_INTERNAL_ERROR: 'La verifica narrativa non è completata',
  DOCUMENT_PROVENANCE_NOT_AVAILABLE: 'La relazione non ha provenienza documentale',
  TRIAL_ASSOCIATION_IS_NOT_EFFICACY_EVIDENCE: 'La presenza nel trial non dimostra efficacia',
  TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE: 'La presenza nel trial non dimostra efficacia',
  CANDIDATE_PARTIALLY_SUPPORTED: 'Limitazioni di corrispondenza registrate: consultare osservazioni e controlli',
  QUOTE_INVALID: 'La citazione non è stata validata',
  PUBLICATION_INCOMPLETE_RUN_PARTIAL: 'Riconciliazione PASS; pubblicazione incompleta perché la run è parziale',
  RECONCILIATION_NOT_CONFIRMED_PASS: 'La riconciliazione delle evidenze non è confermata PASS',
  READER_ABSTAINED: 'Il sistema non ha ottenuto un arricchimento documentale',
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return 'non disponibile';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}
