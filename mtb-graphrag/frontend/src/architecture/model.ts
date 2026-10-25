export type GateState = 'PASS' | 'MISMATCH' | 'UNRESOLVED' | 'INFO';

export interface ArchitectureNode {
  id: string;
  title: string;
  group: string;
  description: string;
  io: string;
  x: number;
  y: number;
  kind?: 'terminal' | 'gate' | 'branch';
}

export interface ArchitectureEdge {
  id: string;
  from: string;
  to: string;
  label?: string;
  bend?: number;
}

export interface SimulationEvent {
  nodeId: string;
  edgeId?: string;
  title: string;
  operation: string;
  state: GateState;
  input: string;
  output: string;
  note?: string;
}

export interface DemoScenario {
  id: string;
  title: string;
  subtitle: string;
  family: string;
  dossierStatus: string;
  dossierLabel: string;
  source: string;
  recordState: string;
  events: SimulationEvent[];
}

// Declarative architecture of the frozen GCA4 runtime. Coordinates are in the
// virtual SVG canvas and never depend on a simulation timer.
export const architectureNodes: ArchitectureNode[] = [
  { id: 'case', title: 'Caso clinico', group: 'INPUT CLINICO', description: 'Testo del caso fornito dall’utente. La demo non invia né conserva casi reali.', io: 'Input: testo libero', x: 60, y: 92 },
  { id: 'parser', title: 'Case Parser 3.5', group: 'COMPRENSIONE', description: 'Estrae il contesto molecolare strutturato e mantiene UNKNOWN dove il testo non specifica un campo.', io: 'Input: testo · Output: menzioni e CaseContext', x: 335, y: 92 },
  { id: 'context', title: 'CaseContext', group: 'COMPRENSIONE', description: 'Rappresentazione normalizzata di patologia, gene, variante e trattamenti; le menzioni sono confrontate con il testo.', io: 'Input: parsing · Output: contesto verificato', x: 610, y: 92 },
  { id: 'gca', title: 'GCA + Selector', group: 'KNOWLEDGE GRAPH', description: 'Seleziona relazioni candidate dal grafo. Una relazione GCA è un target strutturato, non verità clinica indipendente.', io: 'Input: CaseContext · Output: relazioni candidate', x: 885, y: 92 },
  { id: 'documents', title: 'PMID / NCT', group: 'DOCUMENTI', description: 'Risoluzione dei riferimenti pubblici e dei documenti disponibili. PAPER e TRIAL mantengono famiglie distinte.', io: 'Input: identificativi · Output: fonti risolte', x: 1160, y: 92 },
  { id: 'sourceunits', title: 'JATS 1.1 SourceUnits', group: 'DOCUMENTI', description: 'Il parser segmenta il testo in unità citabili e contesto documentale con provenienza.', io: 'Input: XML JATS · Output: unità e riferimenti', x: 1435, y: 92 },
  { id: 'rrf', title: 'BM25_STRUCTURE + MedCPT RRF', group: 'RETRIEVAL', description: 'La selezione canonica fonde i ranking strutturale e MedCPT (k=60, pesi 1:1, shortlist 25); top-5 e cap di due documenti per associazione. BM25_STRUCTURE è fallback esplicito.', io: 'Input: SourceUnits eleggibili · Output: contesto top-5', x: 1710, y: 92 },
  { id: 'reader', title: 'Reader 4.9', group: 'ESTRAZIONE', description: 'Estrae osservazioni e citazioni dalle sole unità selezionate. Può restituire ABSTAIN.', io: 'Input: contesto autorizzato · Output: QUOTE o ABSTAIN', x: 1985, y: 92 },
  { id: 'quote', title: 'Quote validator', group: 'VERIFICA', description: 'Controlla che la citazione sia letterale e appartenga alla SourceUnit con provenienza autorizzata.', io: 'Input: quote + fonte · Output: autenticata / bloccata', x: 1985, y: 330, kind: 'gate' },
  { id: 'structural', title: 'Gate strutturale', group: 'VERIFICA', description: 'Valuta identità e compatibilità documentale. PASS è un prerequisito per semantic alignment EVIDENCE_DRUG, non prova di supporto.', io: 'Input: quote autentica + target · PASS / MISMATCH / UNRESOLVED', x: 1710, y: 330, kind: 'gate' },
  { id: 'semantic', title: 'Semantic alignment 2.1', group: 'VERIFICA SCIENTIFICA', description: 'Chiamato per EVIDENCE_DRUG solo dopo autenticazione e gate strutturale PASS. L’ammissione resta deterministica; la correttezza scientifica non è validata dalla demo.', io: 'Input: target + evidenza · Output: allineamento e limiti', x: 1435, y: 330 },
  { id: 'statement', title: 'Policy EVIDENCE_STATEMENT', group: 'VERIFICA', description: 'Percorso deterministico separato: non chiama il semantic verifier.', io: 'Input: quote autenticata · Output: esito policy', x: 1160, y: 330 },
  { id: 'disposition', title: 'Esito del record', group: 'DOSSIER', description: 'Conserva gli esiti ammessi, bloccati, contraddittori o non risolti con stato e motivazione distinti.', io: 'Input: policy per famiglia · Output: record e limiti', x: 885, y: 330, kind: 'branch' },
  { id: 'dossier', title: 'Dossier + accounting', group: 'DOSSIER', description: 'Riconcilia operazioni pianificate e completate; provenienza e diagnostica restano associate ai record.', io: 'Input: record + run ledger · Output: dossier e riconciliazione', x: 610, y: 330 },
  { id: 'presentation', title: 'JSON / Markdown', group: 'PRESENTAZIONE', description: 'Espone risultati e limitazioni. Completo solo con operazioni completate e accounting PASS; dossier parziali mantengono l’avviso.', io: 'Input: dossier · Output: vista verificabile', x: 335, y: 330, kind: 'terminal' },
];

export const architectureEdges: ArchitectureEdge[] = [
  { id: 'case-parser', from: 'case', to: 'parser' },
  { id: 'parser-context', from: 'parser', to: 'context' },
  { id: 'context-gca', from: 'context', to: 'gca' },
  { id: 'gca-documents', from: 'gca', to: 'documents', label: 'PAPER / TRIAL' },
  { id: 'documents-sourceunits', from: 'documents', to: 'sourceunits' },
  { id: 'sourceunits-rrf', from: 'sourceunits', to: 'rrf' },
  { id: 'rrf-reader', from: 'rrf', to: 'reader' },
  { id: 'reader-quote', from: 'reader', to: 'quote' },
  { id: 'quote-structural', from: 'quote', to: 'structural' },
  { id: 'structural-semantic', from: 'structural', to: 'semantic', label: 'PASS · EVIDENCE_DRUG' },
  { id: 'quote-statement', from: 'quote', to: 'statement', label: 'EVIDENCE_STATEMENT · policy deterministica' },
  { id: 'quote-trial', from: 'quote', to: 'disposition', label: 'TRIAL · record con provenance' },
  { id: 'structural-blocked', from: 'structural', to: 'disposition', label: 'MISMATCH / UNRESOLVED' },
  { id: 'semantic-disposition', from: 'semantic', to: 'disposition' },
  { id: 'statement-disposition', from: 'statement', to: 'disposition' },
  { id: 'disposition-dossier', from: 'disposition', to: 'dossier' },
  { id: 'dossier-presentation', from: 'dossier', to: 'presentation' },
  { id: 'gca-kg-only', from: 'gca', to: 'disposition', label: 'KG_ONLY · solo provenienza GCA', bend: 515 },
];

const event = (nodeId: string, title: string, operation: string, state: GateState, input: string, output: string, edgeId?: string, note?: string): SimulationEvent => ({ nodeId, edgeId, title, operation, state, input, output, note });

const commonStart = (): SimulationEvent[] => [
  event('case', 'Ingresso del caso', 'Il testo entra nella pipeline dimostrativa.', 'INFO', '«Caso demo: adenocarcinoma esempio, ALK variante X; relazione illustrativa»', 'Testo sintetico DEMO; non è un caso clinico reale.'),
  event('parser', 'Estrazione strutturata', 'Il parser costruisce menzioni senza colmare campi assenti.', 'INFO', 'Testo sintetico', 'disease=esempio · gene=ALK · variant=X · assenti=UNKNOWN', 'case-parser'),
  event('context', 'Contesto verificato', 'Le menzioni strutturate vengono confrontate con il testo sorgente.', 'PASS', 'Menzioni + spans sorgente', 'CaseContext con provenance delle menzioni', 'parser-context'),
  event('gca', 'Recupero relazioni GCA', 'Il selector restituisce candidati; la relazione non è una conclusione clinica.', 'INFO', 'CaseContext', 'Candidate relation + family + PMID/NCT', 'context-gca'),
];

export const demoScenarios: DemoScenario[] = [
  {
    id: 'retrieval', title: 'A · Evidence retrieval', subtitle: 'Una citazione supera i controlli documentali; i controlli successivi dipendono dalla famiglia documentale.', family: 'PAPER · EVIDENCE_STATEMENT', dossierStatus: 'COMPLETED · ACCOUNTING PASS', dossierLabel: 'Record documentale conservato', source: 'PMID DEMO-001 · SourceUnit DEMO-SU-04', recordState: 'QUOTE autenticata · policy deterministica',
    events: [...commonStart(), event('documents', 'Risoluzione documento', 'Il riferimento pubblico della relazione individua la fonte disponibile.', 'PASS', 'PMID DEMO-001', 'Documento demo risolto', 'gca-documents'), event('sourceunits', 'Segmentazione documentale', 'Il documento JATS viene rappresentato in unità con identificativi e provenance.', 'PASS', 'JATS demo', 'SourceUnits citabili + contesto bounded', 'documents-sourceunits'), event('rrf', 'Selezione SourceUnit', 'RRF ordina le unità eleggibili; il fallback, se usato, è esplicito.', 'PASS', 'BM25_STRUCTURE + MedCPT', 'Top-5 · cap 2 documenti · component ranks', 'sourceunits-rrf'), event('reader', 'Estrazione Reader', 'Il Reader restituisce un’osservazione con citazione letterale.', 'PASS', 'SourceUnits selezionate', 'QUOTE · osservazione sintetica', 'rrf-reader'), event('quote', 'Autenticazione letterale', 'La citazione coincide con testo della SourceUnit autorizzata.', 'PASS', 'Quote + SourceUnit', 'Quote autenticata con source id', 'reader-quote'), event('statement', 'Policy deterministica', 'EVIDENCE_STATEMENT segue il proprio controllo ancorato al documento, senza structural drug gate né semantic alignment.', 'PASS', 'Relazione + quote autenticata', 'Esito documentale della policy', 'quote-statement'), event('disposition', 'Record conservato', 'La presenza nel dossier descrive un esito documentale, non efficacia clinica.', 'PASS', 'Esito policy', 'Record con stato e riferimenti', 'statement-disposition'), event('dossier', 'Riconciliazione', 'Accounting confronta lavoro pianificato ed esiti prodotti.', 'PASS', 'Ledger + records', 'Accounting PASS', 'disposition-dossier'), event('presentation', 'Dossier presentato', 'JSON e Markdown espongono source, stato e limiti.', 'PASS', 'Dossier riconciliato', 'Vista dimostrativa completa', 'dossier-presentation')],
  },
  {
    id: 'structural-rejection', title: 'B · Structural rejection', subtitle: 'Una citazione autentica ma incompatibile viene bloccata prima del semantic verifier.', family: 'PAPER · EVIDENCE_DRUG', dossierStatus: 'COMPLETED · ACCOUNTING PASS', dossierLabel: 'Record bloccato con motivo', source: 'PMID DEMO-002 · SourceUnit DEMO-SU-09', recordState: 'MISMATCH · semantic calls: 0',
    events: [...commonStart(), event('documents', 'Fonte risolta', 'Il documento è disponibile per la relazione candidata.', 'PASS', 'PMID DEMO-002', 'Documento demo risolto', 'gca-documents'), event('sourceunits', 'Unità citabili', 'Il parser conserva la provenienza dei passaggi.', 'PASS', 'JATS demo', 'SourceUnit DEMO-SU-09', 'documents-sourceunits'), event('rrf', 'Ranking ibrido', 'RRF seleziona il passaggio sulla base dei ranking, non del supporto scientifico.', 'PASS', 'SourceUnits eleggibili', 'Passaggio incluso nel top-5', 'sourceunits-rrf'), event('reader', 'Quote estratta', 'Il Reader estrae una citazione che parla di un intervento diverso dal target.', 'PASS', 'Passaggio selezionato', 'QUOTE letterale · farmaco nel testo ≠ target', 'rrf-reader'), event('quote', 'Citazione autentica', 'L’autenticità viene confermata: questo non dimostra che la quote sia pertinente.', 'PASS', 'Testo citato', 'Quote autentica', 'reader-quote'), event('structural', 'Mismatch dimostrato', 'Il gate rileva incompatibilità dell’identità del farmaco e blocca il candidato.', 'MISMATCH', 'Target drug A · quote riferita a drug B', 'Record escluso · semantic verifier NON eseguito', 'quote-structural', 'Autentica ≠ pertinente ≠ supporto.'), event('disposition', 'Blocco tracciato', 'La motivazione e la provenance restano nel dossier come record non ammesso.', 'MISMATCH', 'Gate strutturale MISMATCH', 'Bloccato con reason code', 'structural-blocked'), event('dossier', 'Accounting della run', 'Il blocco è un esito contabilizzato, non una perdita silenziosa.', 'PASS', 'Candidate + disposition', 'Riconciliazione PASS', 'disposition-dossier'), event('presentation', 'Limitazione visibile', 'La vista mostra l’esclusione e non la presenta come evidenza supportiva.', 'PASS', 'Dossier', 'Record bloccato e spiegazione', 'dossier-presentation')],
  },
  {
    id: 'semantic', title: 'C · Semantic verification', subtitle: 'EVIDENCE_DRUG raggiunge il verificatore solo dopo autenticazione e structural PASS.', family: 'PAPER · EVIDENCE_DRUG', dossierStatus: 'COMPLETED · ACCOUNTING PASS', dossierLabel: 'Esito simulato e limitato', source: 'PMID DEMO-003 · SourceUnit DEMO-SU-02', recordState: 'Semantic review SIMULATED · non clinicamente validata',
    events: [...commonStart(), event('documents', 'Riferimento risolto', 'La relazione candidata punta a una pubblicazione disponibile.', 'PASS', 'PMID DEMO-003', 'Documento demo risolto', 'gca-documents'), event('sourceunits', 'SourceUnits pronte', 'Unità citabili e contesto restano collegati alla fonte.', 'PASS', 'JATS demo', 'SourceUnit + provenance', 'documents-sourceunits'), event('rrf', 'RRF top-5', 'I ranking strutturale e MedCPT si fondono prima della selezione finale.', 'PASS', 'Due liste di ranking', 'Top-5 SourceUnits demo', 'sourceunits-rrf'), event('reader', 'Osservazione estratta', 'Il Reader propone una quote e un’osservazione per il target.', 'PASS', 'SourceUnit selezionata', 'QUOTE + observation demo', 'rrf-reader'), event('quote', 'Autenticazione', 'La quote è letterale e la fonte è autorizzata.', 'PASS', 'QUOTE + reference', 'Prerequisito documentale PASS', 'reader-quote'), event('structural', 'Prerequisiti strutturali', 'Nessuna incompatibilità nota; il gate PASS apre il semantic alignment.', 'PASS', 'Identità + target + quote', 'EVIDENCE_DRUG eligible for semantic review', 'quote-structural'), event('semantic', 'Semantic alignment · simulato', 'Il verificatore confronta claim, risultato osservato e scope. Questa demo non esegue un LLM.', 'INFO', 'Evidenza demo prima del target', 'SIMULATED: PARTIAL_SUPPORT · scope limitato', 'structural-semantic', 'L’esito è una fixture dimostrativa, non un giudizio scientifico reale.'), event('disposition', 'Ammissione deterministica', 'La policy converte l’output strutturato nei soli stati consentiti.', 'INFO', 'Semantic output simulato', 'Record demo con limitazione conservata', 'semantic-disposition'), event('dossier', 'Accounting PASS', 'Il dossier aggrega record e stato di riconciliazione.', 'PASS', 'Record + ledger demo', 'Accounting PASS', 'disposition-dossier'), event('presentation', 'Dossier dimostrativo', 'Il record mostra provenienza e natura simulata dell’esito.', 'INFO', 'Dossier', 'Nessuna validazione clinica implicata', 'dossier-presentation')],
  },
  {
    id: 'families-statement', title: 'D1 · EVIDENCE_STATEMENT', subtitle: 'La citazione autenticata passa alla policy deterministica, senza structural drug gate o semantic alignment.', family: 'PAPER · EVIDENCE_STATEMENT', dossierStatus: 'COMPLETED · ACCOUNTING PASS', dossierLabel: 'Provenienza e policy conservate', source: 'PMID DEMO-005 · SourceUnit DEMO-SU-05', recordState: 'Policy deterministica · nessun semantic call',
    events: [...commonStart(), event('documents', 'Documento PAPER', 'La relazione risolve un riferimento pubblicazione disponibile.', 'PASS', 'PMID DEMO-005', 'Documento demo', 'gca-documents'), event('sourceunits', 'SourceUnit materiale', 'Il testo citabile mantiene ID e provenienza.', 'PASS', 'JATS demo', 'SourceUnits con provenance', 'documents-sourceunits'), event('rrf', 'Ranking RRF', 'Le unità eleggibili vengono selezionate con la strategia canonica o fallback tracciato.', 'PASS', 'BM25_STRUCTURE + MedCPT', 'Top-5 SourceUnits', 'sourceunits-rrf'), event('reader', 'Estrazione Reader', 'Il Reader restituisce quote o astensione sul testo selezionato.', 'PASS', 'SourceUnits', 'QUOTE demo', 'rrf-reader'), event('quote', 'Validazione documentale', 'La quote letterale e la provenienza sono validate.', 'PASS', 'Quote + source reference', 'QUOTE autenticata', 'reader-quote'), event('statement', 'Policy deterministica', 'EVIDENCE_STATEMENT usa la policy documentale; non esegue il gate drug o semantico.', 'PASS', 'Claim + quote', 'Esito della policy statement', 'quote-statement'), event('disposition', 'Record PAPER', 'L’esito resta una verifica documentale e non un risultato clinico.', 'INFO', 'Policy statement', 'Record con limiti e provenienza', 'statement-disposition'), event('dossier', 'Dossier', 'Il record conserva family, source e stato.', 'PASS', 'Record verificato', 'Dossier demo', 'disposition-dossier'), event('presentation', 'Vista dossier', 'Stato, riferimenti e limiti restano visibili.', 'PASS', 'Dossier demo', 'Nessuna raccomandazione terapeutica', 'dossier-presentation')],
  },
  {
    id: 'families-trial', title: 'D2 · TRIAL record', subtitle: 'Il trial segue il percorso documentale disponibile e conserva la famiglia TRIAL; associazione non equivale a efficacia o eleggibilità.', family: 'TRIAL · NCT DEMO-006', dossierStatus: 'COMPLETED · ACCOUNTING PASS', dossierLabel: 'Record di trial con limiti', source: 'NCT DEMO-006 · trial context DEMO', recordState: 'Non è una valutazione di eleggibilità o efficacia',
    events: [...commonStart(), event('documents', 'Risoluzione trial', 'Il riferimento NCT risolve un record di registro.', 'PASS', 'NCT DEMO-006', 'Trial registry record DEMO', 'gca-documents'), event('sourceunits', 'Contesto trial', 'Il record disponibile produce unità di testo collegate al riferimento pubblico.', 'INFO', 'Trial record demo', 'Unità testuali con provenance NCT', 'documents-sourceunits'), event('rrf', 'Selezione del contesto', 'Il ranking ordina le unità eleggibili per il Reader.', 'PASS', 'Unità trial disponibili', 'Contesto selezionato con RRF', 'sourceunits-rrf'), event('reader', 'Estrazione dal record', 'Il Reader estrae contenuto testuale; non determina se il paziente è eleggibile.', 'INFO', 'Contesto trial selezionato', 'QUOTE demo oppure astensione', 'rrf-reader'), event('quote', 'Provenienza del testo', 'La citazione può essere autenticata rispetto alla fonte; questo non dimostra efficacia.', 'PASS', 'Testo + NCT', 'Riferimento documentale conservato', 'reader-quote'), event('disposition', 'Famiglia TRIAL', 'La relazione rimane un record di studio, senza promozione a efficacia terapeutica o idoneità individuale.', 'INFO', 'TRIAL + record autenticato', 'Record TRIAL con limiti', 'quote-trial'), event('dossier', 'Dossier distinto', 'Il dossier conserva la famiglia TRIAL separata dai paper e dal KG_ONLY.', 'PASS', 'Record trial', 'Provenienza NCT nel dossier', 'disposition-dossier'), event('presentation', 'Limiti visibili', 'La vista espone lo stato del record senza inferire un esito clinico.', 'PASS', 'Dossier trial', 'Nessuna inferenza di efficacia', 'dossier-presentation')],
  },
  {
    id: 'families-kg', title: 'D3 · KG_ONLY', subtitle: 'La relazione mantiene la provenienza GCA e raggiunge il dossier senza document retrieval o Reader.', family: 'KG_ONLY · provenance GCA', dossierStatus: 'COMPLETED · ACCOUNTING PASS', dossierLabel: 'Relazione del grafo, non evidenza documentale', source: 'GCA relation DEMO-007', recordState: 'Nessun PMID/NCT documentale associato',
    events: [...commonStart(), event('disposition', 'Ramo KG_ONLY', 'Senza una fonte documentale associata, la relazione conserva soltanto il record e la provenance GCA.', 'INFO', 'GCA relation DEMO-007', 'KG_ONLY record · Reader non eseguito', 'gca-kg-only'), event('dossier', 'Dossier KG_ONLY', 'Il record viene contabilizzato come relazione del grafo, non come supporto verificato.', 'PASS', 'KG provenance', 'Record distinto per famiglia', 'disposition-dossier'), event('presentation', 'Provenienza esplicita', 'La vista distingue il contenuto GCA dall’evidenza documentale.', 'PASS', 'Dossier KG_ONLY', 'Nessuna evidenza clinica implicata', 'dossier-presentation')],
  },
  {
    id: 'fallback-partial', title: 'E · Fallback + partial dossier', subtitle: 'L’errore MedCPT attiva un fallback tracciato; un accounting non riuscito impedisce la pubblicazione come completo.', family: 'PAPER · run parziale', dossierStatus: 'PARTIAL · ACCOUNTING FAIL', dossierLabel: 'Diagnostica conservata · non completo', source: 'PMID DEMO-004 · SourceUnit DEMO-SU-01', recordState: 'Fallback BM25_STRUCTURE tracciato',
    events: [...commonStart(), event('documents', 'Fonte risolta', 'La fonte è disponibile; il fetch non viene simulato come chiamata reale.', 'PASS', 'PMID DEMO-004', 'Documento demo', 'gca-documents'), event('sourceunits', 'Unità disponibili', 'Il testo è già presente nel fixture dimostrativo.', 'PASS', 'JATS demo pre-caricato', 'SourceUnits con identificativi', 'documents-sourceunits'), event('rrf', 'Fallback esplicito', 'Il backend MedCPT non è disponibile: la baseline BM25_STRUCTURE viene usata e registrata.', 'UNRESOLVED', 'RRF richiesto · MedCPT unavailable', 'BM25_STRUCTURE fallback · strategy tracciata', 'sourceunits-rrf'), event('reader', 'Estrazione parziale', 'Il Reader produce un output di fixture; la demo non chiama provider.', 'INFO', 'SourceUnits del fixture', 'QUOTE/record già prodotto conservato', 'rrf-reader'), event('quote', 'Stato documentale conservato', 'La provenienza rimane disponibile anche se la run si interrompe successivamente.', 'PASS', 'Record acquisito', 'Riferimenti mantenuti', 'reader-quote'), event('structural', 'Verifica non eseguita', 'Un passaggio pianificato rimasto ineseguito è marcato come tale.', 'UNRESOLVED', 'Run interrotta prima della riconciliazione', 'Gate strutturale non eseguito · diagnostica conservata', 'quote-structural'), event('dossier', 'Accounting FAIL', 'Il dossier resta consultabile ma non è dichiarato riconciliato o completo.', 'MISMATCH', 'Expected work ≠ completed work', 'publication_status=INCOMPLETE', 'disposition-dossier', 'Un accounting FAIL non cancella record né li promuove.'), event('presentation', 'Avviso di pubblicazione', 'JSON e Markdown devono esporre PARTIAL e il fallimento di accounting.', 'MISMATCH', 'Dossier diagnostico', 'Avviso visibile · complete=false', 'dossier-presentation')],
  },
];

export function nodeById(id: string): ArchitectureNode | undefined {
  return architectureNodes.find((node) => node.id === id);
}
