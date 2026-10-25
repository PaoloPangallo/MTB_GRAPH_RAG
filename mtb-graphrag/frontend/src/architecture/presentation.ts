/** UI descriptions only. Scientific states and demo timelines live in model.ts. */
export const nodeCopy: Record<string, { title: string; summary: string; phase: string; version?: string }> = {
  case: { title: 'Caso clinico', summary: 'Il punto di partenza è il testo del caso.', phase: 'Comprensione' },
  parser: { title: 'Case Parser', summary: 'Estrae patologia, geni, varianti e trattamenti.', phase: 'Comprensione', version: '3.5' },
  context: { title: 'CaseContext', summary: 'Normalizza le menzioni e le riscontra nel testo.', phase: 'Comprensione' },
  gca: { title: 'Relazioni GCA', summary: 'Il selector individua le relazioni candidate.', phase: 'Retrieval' },
  documents: { title: 'Pubblicazioni e trial', summary: 'Risolve i riferimenti PMID e NCT.', phase: 'Retrieval' },
  sourceunits: { title: 'SourceUnit', summary: 'Divide il documento in passaggi tracciabili.', phase: 'Retrieval', version: 'JATS 1.1' },
  rrf: { title: 'Retrieval RRF', summary: 'BM25_STRUCTURE e MedCPT selezionano il contesto.', phase: 'Retrieval' },
  reader: { title: 'Reader', summary: 'Estrae una citazione oppure si astiene.', phase: 'Estrazione', version: '4.9' },
  quote: { title: 'Citazione letterale', summary: 'La citazione appartiene davvero alla fonte?', phase: 'Verifica' },
  structural: { title: 'Compatibilità strutturale', summary: 'Gene, variante e intervento sono compatibili?', phase: 'Verifica' },
  semantic: { title: 'Verifica semantica', summary: 'Il testo sostiene il target e con quali limiti?', phase: 'Verifica', version: '2.1' },
  statement: { title: 'Policy deterministica', summary: 'Verifica le relazioni EVIDENCE_STATEMENT.', phase: 'Verifica' },
  disposition: { title: 'Esito del record', summary: 'Conserva l’esito, il motivo e la provenienza.', phase: 'Dossier' },
  dossier: { title: 'Dossier e accounting', summary: 'Riconcilia le operazioni e i record prodotti.', phase: 'Dossier' },
  presentation: { title: 'JSON e Markdown', summary: 'Rende visibili evidenze, stati e limiti.', phase: 'Presentazione' },
};

export const scenarioCopy: Record<string, { title: string; question: string }> = {
  retrieval: { title: 'A · Citazione verificabile', question: 'Come si passa da un caso a una citazione con fonte verificabile?' },
  'structural-rejection': { title: 'B · Citazione incompatibile', question: 'Cosa succede quando la citazione è autentica ma parla di un altro farmaco?' },
  semantic: { title: 'C · Verifica semantica', question: 'Quando viene chiamato il verificatore semantico?' },
  'families-statement': { title: 'D1 · Relazione scientifica', question: 'Come funziona il percorso deterministico EVIDENCE_STATEMENT?' },
  'families-trial': { title: 'D2 · Registro di trial', question: 'Quali informazioni conserva un record di studio clinico?' },
  'families-kg': { title: 'D3 · Solo Knowledge Graph', question: 'Come viene conservata una relazione senza fonte documentale?' },
  'fallback-partial': { title: 'E · Fallback e run parziale', question: 'Cosa resta nel dossier quando l’elaborazione non si completa?' },
};
