import { Alert, Box, Button, Divider, InputAdornment, Link, Stack, TextField, Typography } from '@mui/material';
import { memo, useState, type ReactNode } from 'react';
import SearchOutlined from '@mui/icons-material/SearchOutlined';
import ArticleOutlined from '@mui/icons-material/ArticleOutlined';
import ScienceOutlined from '@mui/icons-material/ScienceOutlined';
import HubOutlined from '@mui/icons-material/HubOutlined';
import { color, font, radius, reasonLabel, sourceStyle, workspaceOffset } from './tokens';
import PublicationNotice from './PublicationNotice';
import { documentaryChecks } from './documentaryFindings';
import DocumentaryObservation from './DocumentaryObservation';
import type { DocumentaryFinding, DossierReadingGuide } from './contracts.generated';
import { readingFor } from './readingGuide';
import StructuredValue from './values/StructuredValue';
import BoundedValue from './values/BoundedValue';
import CaseSummaryView from './CaseSummaryView';
import TrialStudies from './TrialStudies';
import { entrySearchText, studyGroups } from './dossierReading';
import { graphEntityLabel, type GraphEntity } from './graphEntityLabel';
import type { CaseSummary, RetrievalSummary, EvidenceRecord } from './contracts.generated';
export type { EvidenceRecord } from './contracts.generated';

export interface CanonicalEntry {
  candidate_id: string;
  documentary_target?: Record<string, unknown> | null;
  documentary_findings?: DocumentaryFinding[] | null;
  documentary_attempts?: Record<string, unknown>[] | null;
  relation?: string;
  direction?: string | null;
  subject?: GraphEntity | null;
  object?: GraphEntity | null;
  document_id?: string | null;
  representative_document_id?: string | null;
  declared_source_identity?: string | null;
  nct_id?: string | null;
  title?: string | null;
  status?: string | null;
  phase?: string[] | string | null;
  conditions?: unknown[];
  interventions?: unknown[];
  arm_groups?: Record<string, unknown>[];
  arm_group_status?: string | null;
  trial_structure_provenance?: Record<string, unknown> | null;
  quote?: string | null;
  quote_source_unit_id?: string | null;
  quote_valid?: boolean | null;
  support_level?: string | null;
  support_fields?: Record<string, unknown> | null;
  support_reason?: string | null;
  accepted_evidence_records?: EvidenceRecord[];
  rejected_evidence?: EvidenceRecord[];
  evidence_composition?: { record_count?: number; unique_publication_count?: number; mixed_support?: boolean; counts_by_support_result?: Record<string, number> };
  contradiction_present?: boolean;
  reader_attempts?: EvidenceRecord[];
  claim?: Record<string, unknown>;
  source?: string | null;
  source_database?: string | null;
  provenance_status?: string | null;
  eligibility_status?: string | null;
  trial_resolution_status?: string | null;
  disease_context?: unknown[];
  graph_provenance?: Record<string, unknown>;
}
export interface Dossier {
  reading_guide?: DossierReadingGuide | null;
  documentary_contract_version?: string | null;
  documentary_summary?: Record<string, unknown> | null;
  documentary_projection_migration?: Record<string, unknown> | null;
  run_status?: string;
  technical_run_status?: string;
  publication_status?: string;
  publication_integrity?: { reconciliation_status?: string; reason_codes?: string[] };
  case_summary?: CaseSummary;
  retrieval_summary?: RetrievalSummary;
  pipeline_accounting?: Record<string, unknown>;
  paper_evidence?: CanonicalEntry[];
  clinical_trials?: CanonicalEntry[];
  kg_only_relations?: CanonicalEntry[];
  limitations?: string[];
  source_unit_retrieval?: {
    strategies_used?: string[];
    fallbacks?: { candidate_id?: string; document_id?: string; reason?: string }[];
    selections?: { excluded_documents?: { reason_codes?: string[] }[] }[];
  };
}
// Solo identificatori riconosciuti diventano link: nessun URL del modello.
function sourceUrl(id: string): string | null {
  if (/^pmid:\d+$/i.test(id)) return `https://pubmed.ncbi.nlm.nih.gov/${id.split(':')[1]}/`;
  if (/^(?:pmcid:)?PMC\d+$/i.test(id)) return `https://pmc.ncbi.nlm.nih.gov/articles/${id.replace(/^pmcid:/i, '').toUpperCase()}/`;
  if (/^(?:nct:)?NCT\d{8}$/i.test(id)) return `https://clinicaltrials.gov/study/${id.replace(/^nct:/i, '').toUpperCase()}`;
  return null;
}
function Source({ id }: { id?: string | null }) {
  if (!id) return <Typography variant="body2">Fonte non disponibile</Typography>;
  const href = sourceUrl(id);
  return href ? <Link href={href} target="_blank" rel="noopener noreferrer" sx={{ overflowWrap: 'anywhere' }}>{id}</Link>
    : <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{id}</Typography>;
}
function Evidence({ record, debug }: { record: EvidenceRecord; debug: boolean }) {
  const checks = documentaryChecks(record);
  const valid = record.quote_valid === true || (record.quote_valid !== false && record.presentation_state === 'VALIDATED_QUOTE');
  const quote = valid ? record.quote ?? record.author_claim_quote : null;
  return <Box sx={{ py: 1.5, borderTop: `1px solid ${color.hairline}` }}>
    <Stack direction="row" spacing={2} sx={{ alignItems: 'baseline', flexWrap: 'wrap' }}>
      <Source id={record.document_id ?? record.paper_id} />
      <Typography variant="body2" sx={{ color: color.slate }}>{record.source_unit_id ?? 'Source Unit non disponibile'}</Typography>
    </Stack>
    {quote ? <Typography component="blockquote" sx={{ m: 0, mt: 1, p: 1.5, bgcolor: color.stone, borderRadius: `${radius.sm}px`, lineHeight: 1.65, overflowWrap: 'anywhere' }}>“{quote}”</Typography>
      : <Typography variant="body2" sx={{ mt: 1 }}>Nessuna citazione validata disponibile.</Typography>}
    <Typography variant="body2" sx={{ mt: 1 }}>Citazione: {checks.quotation} · Gate strutturale: {checks.structural} · Verifica semantica: {checks.semantic}</Typography>
    {record.observed_relation && <Box sx={{ mt: 1.5 }}><Typography variant="body2" sx={{ fontWeight: 600 }}>Osservazione estratta dal Reader</Typography><Typography variant="body2" sx={{ color: color.slate }}>Campi estratti, non giudizi clinici indipendenti. I valori mancanti restano non specificati.</Typography><StructuredValue value={{ soggetti: record.observed_relation.subjects, intervento: record.observed_relation.intervention, malattia: record.observed_relation.disease, risultato: record.observed_relation.effect_direction, contesto: record.observed_relation.evidence_context, incertezza: record.observed_relation.uncertainty, limitazioni: record.observed_relation.caveats }} /></Box>}
    {(record.candidate_support || record.document_verification || record.support_level) && <DeferredDetails title="Controlli e classificazione tecnica registrata"><StructuredValue value={{ candidate_support: record.candidate_support, document_verification: record.document_verification, historical_support_level: record.support_level }} /></DeferredDetails>}
    {debug && record.candidate_support && <StructuredValue value={record.candidate_support} />}
    {debug && record.document_verification && <StructuredValue value={record.document_verification} />}
  </Box>;
}
function DeferredDetails({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  return <Box component="details" onToggle={event => setOpen(event.currentTarget.open)} sx={{ mt: 2, '& summary': { cursor: 'pointer', color: color.actionBlue, fontSize: 13 }, overflowWrap: 'anywhere' }}>
    <summary>{title}</summary>
    {open && children}
  </Box>;
}
function Details({ entry }: { entry: CanonicalEntry }) {
  return <DeferredDetails title="Tracciabilità e dettagli della relazione">
    <Box sx={{ mt: 1.5 }}>
      <BoundedValue value={{ candidate_id: entry.candidate_id, relation: entry.relation,
        claim: entry.claim, graph_provenance: entry.graph_provenance, support_fields: entry.support_fields,
        historical_support_level: entry.support_level,
        support_reason: entry.support_reason, declared_source_identity: entry.declared_source_identity }} />
      {!!entry.rejected_evidence?.length && <><Typography variant="body2" sx={{ mt: 2 }}>Osservazioni escluse dalla presentazione: {entry.rejected_evidence.length}</Typography>
        <BoundedValue value={entry.rejected_evidence.map(record => ({ evidence_id: record.evidence_id,
          paper_id: record.paper_id, source_unit_id: record.source_unit_id, validation_outcome: record.validation_outcome,
          candidate_support: record.candidate_support, reason_codes: record.reason_codes }))} /></>}
    </Box>
  </DeferredDetails>;
}
function Section({ title, entries, kind, debug, searching = false, guide }: { title: string; entries: CanonicalEntry[]; kind: 'paper' | 'trial' | 'kg'; debug: boolean; searching?: boolean; guide?: DossierReadingGuide | null }) {
  const [shown, setShown] = useState(8);
  const visible = debug ? entries : entries.slice(0, shown);
  const Icon = kind === 'paper' ? ArticleOutlined : kind === 'trial' ? ScienceOutlined : HubOutlined;
  return <Box component="section" id={`dossier-${kind}`} sx={{ minWidth: 0, mb: 4, scrollMarginTop: `${workspaceOffset}px` }}>
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 2, p: 1.5, bgcolor: sourceStyle[kind].bg, borderRadius: '8px', color: sourceStyle[kind].fg }}><Icon /><Typography component="h3" sx={{ fontSize: 20, fontWeight: 600 }}>{title} <Typography component="span" sx={{ fontSize: 14 }}>({entries.length})</Typography></Typography></Stack>
    {!entries.length && <Typography variant="body2" sx={{ color: color.slate }}>{searching ? 'Nessuna relazione corrisponde alla ricerca.' : 'Nessuna relazione in questo percorso.'}</Typography>}
    {!debug && entries.length > 8 && <Typography sx={{ fontSize: 13, color: color.slate, mb: 1.5 }}>Mostrate {visible.length} di {entries.length} relazioni.</Typography>}
    {visible.map(entry => <Box key={entry.candidate_id} sx={{ borderTop: `1px solid ${color.hairline}`, py: 2.5 }}>
      <Typography component="h4" sx={{ fontSize: 16, fontWeight: 600, overflowWrap: 'anywhere' }}>{kind === 'paper' && entry.relation === 'has_evidence_statement' ? `${graphEntityLabel(entry.subject) ?? 'Biomarcatore non registrato'} · Osservazione documentale` : `${graphEntityLabel(entry.subject) ?? 'Soggetto non disponibile'} → ${graphEntityLabel(entry.object) ?? entry.title ?? 'Oggetto non disponibile'}`}</Typography>
      {(debug || kind !== 'paper') && <Typography sx={{ mt: 0.75, fontSize: 14, color: color.body, overflowWrap: 'anywhere' }}>
        Relazione: {entry.relation ?? 'Non disponibile'}{entry.direction ? ` · Direzione nel grafo: ${entry.direction}` : ''}
      </Typography>}
      {kind === 'paper' && <>
        <Typography sx={{ mt: 1, color: color.slate, fontSize: 14 }}>Target del grafo: confrontare con le osservazioni e i controlli riportati sotto.</Typography>
        {entry.evidence_composition && <Typography variant="body2" sx={{ mt: 1 }}>Evidenze ammesse: {entry.evidence_composition.record_count ?? 0} record da {entry.evidence_composition.unique_publication_count ?? 0} pubblicazioni distinte.{entry.evidence_composition.mixed_support ? ' Esiti misti: consultare i singoli record.' : ''}</Typography>}
        {!!entry.rejected_evidence?.length && <DeferredDetails title={`Osservazioni escluse (${entry.rejected_evidence.length})`}><BoundedValue value={entry.rejected_evidence.map(record => ({ evidence_id: record.evidence_id, paper_id: record.paper_id, source_unit_id: record.source_unit_id, validation_outcome: record.validation_outcome, reason_codes: record.reason_codes, document_verification: record.document_verification }))} /></DeferredDetails>}
        {entry.contradiction_present && <Alert severity="warning" sx={{ my: 1.5 }}>Le fonti riportano osservazioni in conflitto. Il dossier conserva entrambe.</Alert>}
        {entry.documentary_target && <DeferredDetails title="Target documentale della ricerca"><StructuredValue value={entry.documentary_target} /></DeferredDetails>}
        {!!entry.documentary_attempts?.length && <DeferredDetails title={`Tentativi Reader e operazioni non eseguite (${entry.documentary_attempts.length})`}><StructuredValue value={entry.documentary_attempts} /></DeferredDetails>}
        {entry.documentary_findings ? entry.documentary_findings.length ? entry.documentary_findings.map((finding, index) => <DocumentaryObservation key={`${finding.evidence_id ?? index}:${finding.disposition}`} finding={finding} reading={readingFor(guide, entry.candidate_id, index)} />) : <Typography variant="body2" sx={{ mt: 1 }}>Nessuna osservazione documentale conservata per questa relazione.</Typography>
          : entry.accepted_evidence_records?.length ? entry.accepted_evidence_records.map((record, index) => <Evidence debug={debug} key={record.evidence_id ?? `${record.paper_id}:${record.source_unit_id}:${index}`} record={record} />)
          : <Evidence debug={debug} record={{ paper_id: entry.representative_document_id ?? entry.document_id, source_unit_id: entry.quote_source_unit_id, quote: entry.quote, quote_valid: entry.quote_valid }} />}
      </>}
      {kind === 'trial' && <>
        <Source id={entry.nct_id} />
        <Box sx={{ minWidth: 0, maxWidth: '100%', overflowX: 'auto', '& .MuiTable-root': { tableLayout: 'fixed' }, '& .MuiTableCell-root': { whiteSpace: 'normal', overflowWrap: 'anywhere' }, '& .MuiTypography-root': { overflowWrap: 'anywhere' } }}><StructuredValue value={{ titolo: entry.title, stato: entry.status, fase: entry.phase, condizioni: entry.conditions,
          interventi: entry.interventions, risoluzione: entry.trial_resolution_status, fonte: entry.source ?? 'ClinicalTrials.gov' }} /></Box>
        <Typography variant="body2" sx={{ mt: 1 }}>Eleggibilità: {entry.eligibility_status === 'NOT_EVALUATED' || !entry.eligibility_status ? 'Eleggibilità del paziente non valutata' : entry.eligibility_status}</Typography>
        <Alert severity="info" sx={{ mt: 1.5 }}>Associazione a trial: non costituisce prova di efficacia terapeutica né valutazione completa dell’eleggibilità del paziente.</Alert>
        {debug && !!entry.reader_attempts?.length && <DeferredDetails title="Osservazioni sul record trial"><BoundedValue value={entry.reader_attempts} /></DeferredDetails>}
      </>}
      {kind === 'kg' && <>
        <Typography variant="body2" sx={{ mt: 1 }}>Relazione del Knowledge Graph · fonte: {entry.source_database ?? 'Non disponibile'}</Typography>
        <Typography variant="body2" sx={{ mt: 1, color: color.slate }}>Nessuna citazione documentale autenticata disponibile per questa relazione nella run.</Typography>
      </>}
      <Details entry={entry} />
    </Box>)}
    {!debug && shown < entries.length && <Button onClick={() => setShown(count => count + 8)} sx={{ mt: 1, textTransform: 'none' }}>Mostra altre relazioni ({entries.length - shown})</Button>}
  </Box>;
}
function DossierView({ dossier, debug = true, section = 'all' }: { dossier: Dossier | null; debug?: boolean; section?: 'all' | 'relations' | 'limits' }) {
  const [query, setQuery] = useState('');
  if (!dossier) return <Typography sx={{ py: 3 }}>Nessun dossier per questa run.</Typography>;
  if (!dossier.paper_evidence && !dossier.clinical_trials && !dossier.kg_only_relations) {
    return <Alert severity="info">Questo dossier usa un contratto storico. Avvia una nuova run per consultare il dossier della pipeline corrente.</Alert>;
  }
  const sections = [
    { id: 'paper', label: 'Pubblicazioni', icon: ArticleOutlined, entries: dossier.paper_evidence ?? [] },
    { id: 'trial', label: 'Studi clinici', icon: ScienceOutlined, entries: dossier.clinical_trials ?? [] },
    { id: 'kg', label: 'Knowledge Graph', icon: HubOutlined, entries: dossier.kg_only_relations ?? [] },
  ];
  const matches = (entry: CanonicalEntry) => entrySearchText(entry).includes(query.trim().toLocaleLowerCase('it'));
  const filtered = (entries: CanonicalEntry[]) => debug ? entries : entries.filter(matches);
  const matchedCount = sections.reduce((sum, section) => sum + filtered(section.entries).length, 0);
  return <Box sx={{ fontFamily: font.body, minWidth: 0, display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: debug || section === 'limits' ? 'minmax(0, 1fr)' : '210px minmax(0, 1fr)' }, gap: { xs: 2, lg: 4 } }}>
    {!debug && section !== 'limits' && <Box component="nav" aria-label="Sezioni del dossier" sx={{ position: { xs: 'static', lg: 'sticky' }, top: workspaceOffset, alignSelf: 'start', py: 1, borderTop: `1px solid ${color.hairline}` }}>
      <Typography sx={{ fontWeight: 600, fontSize: 15, py: 1.5 }}>Nel dossier</Typography>
      <Stack spacing={0.5}>
        <Link href="#dossier-case" sx={{ py: 1, fontSize: 14 }}>Caso</Link>
        {sections.map(section => <Link key={section.id} href={`#dossier-${section.id}`} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1, fontSize: 14, textDecoration: 'none', '&:hover': { textDecoration: 'underline' } }}><section.icon sx={{ fontSize: 18 }} /><Box component="span" sx={{ flex: 1 }}>{section.label}</Box><Typography component="span" sx={{ fontSize: 12, color: color.slate }}>{section.id === 'trial' ? studyGroups(section.entries).length : section.entries.length}</Typography></Link>)}
        {section === 'all' && <Link href="#dossier-limits" sx={{ py: 1, fontSize: 14 }}>Limiti</Link>}
      </Stack>
    </Box>}
    <Box sx={{ minWidth: 0 }}>
    <PublicationNotice dossier={dossier} />
    {dossier.reading_guide && <Typography sx={{ color: color.slate, maxWidth: '75ch', mb: 2 }}>{dossier.reading_guide.verification_note}</Typography>}
    {section !== 'limits' && <Box id="dossier-case" sx={{ mb: 3, scrollMarginTop: `${workspaceOffset}px` }}>
      <Typography component="h2" sx={{ fontSize: 24, fontWeight: 600 }}>Dossier canonico</Typography>
      <Typography sx={{ color: color.slate, maxWidth: '70ch', mt: 1 }}>Cosa cercavamo, cosa riporta la fonte e quali controlli sono stati eseguiti. Citazioni autentiche e controlli superati non dimostrano efficacia clinica. Gli stati tecnici originali restano consultabili nei dettagli.</Typography>
      <Box sx={{ mt: 2 }}>{debug ? <StructuredValue value={dossier.case_summary} /> : <CaseSummaryView value={dossier.case_summary} />}</Box>
    </Box>}
    {!debug && dossier.paper_evidence?.some(entry => entry.contradiction_present || entry.support_level === 'CONTRADICTORY') && <Alert severity="warning" sx={{ mb: 3 }}>Il dossier contiene evidenze in conflitto. Questo avviso resta visibile anche durante la ricerca nelle relazioni.</Alert>}
    {section !== 'limits' && !debug && <Box sx={{ mb: 3 }}><TextField fullWidth size="small" label="Cerca nelle relazioni" placeholder="Gene, farmaco, fonte o titolo del trial" value={query} onChange={event => setQuery(event.target.value)} slotProps={{ input: { startAdornment: <InputAdornment position="start"><SearchOutlined /></InputAdornment> } }} />
      {query.trim() && <Typography role="status" sx={{ mt: 1, color: color.slate, fontSize: 13 }}>{matchedCount} relazioni corrispondenti. {section === 'all' ? 'Le limitazioni del dossier restano visibili.' : 'Le limitazioni sono consultabili nella destinazione Limiti.'}</Typography>}
    </Box>}
    {section !== 'limits' && <>
    <Section key={`paper:${query}`} title="Evidenze da pubblicazioni" entries={filtered(dossier.paper_evidence ?? [])} kind="paper" debug={debug} searching={!debug && !!query.trim() && !!dossier.paper_evidence?.length} guide={dossier.reading_guide} />
    {debug ? <Section title="Studi clinici — associazioni nel grafo" entries={dossier.clinical_trials ?? []} kind="trial" debug /> : <TrialStudies key={`trial:${query}`} entries={dossier.clinical_trials ?? []} guide={dossier.reading_guide} query={query} searching={!!query.trim() && !!dossier.clinical_trials?.length} />}
    <Section key={`kg:${query}`} title="Relazioni del Knowledge Graph" entries={filtered(dossier.kg_only_relations ?? [])} kind="kg" debug={debug} searching={!debug && !!query.trim() && !!dossier.kg_only_relations?.length} />
    </>}
    {section !== 'relations' && <>
    <Divider sx={{ mb: 2 }} />
    <Typography component="h3" id="dossier-limits" sx={{ fontSize: 20, fontWeight: 600, scrollMarginTop: `${workspaceOffset}px` }}>Limitazioni e ciò che non è stato stabilito</Typography>
    {(dossier.limitations ?? []).map(item => <Typography key={item} variant="body2" sx={{ mt: 1 }}>{reasonLabel(item)}</Typography>)}
    {!dossier.limitations?.length && <Typography variant="body2" sx={{ mt: 1 }}>Nessuna limitazione registrata.</Typography>}
    {(debug || section === 'limits') && <DeferredDetails title="Conteggi e percorso di elaborazione">
      <BoundedValue value={{ retrieval: dossier.retrieval_summary, pipeline: dossier.pipeline_accounting }} />
    </DeferredDetails>}
    </>}
    </Box>
  </Box>;
}

export default memo(DossierView);
