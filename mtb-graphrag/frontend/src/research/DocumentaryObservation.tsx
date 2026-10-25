import { Box, Link, Typography } from '@mui/material';
import type { DocumentaryFinding, ReadingFinding } from './contracts.generated';
import ReadingContext from './ReadingContext';
import StructuredValue from './values/StructuredValue';
import { color } from './tokens';
import { useState } from 'react';
import ObservedFields from './ObservedFields';
import { object, text } from './dossierReading';

const labels: Record<string, string> = {
  AUTHENTICATED: 'Autenticata', REJECTED: 'Non autenticata', NOT_RECORDED: 'Non registrato',
  NOT_EXECUTED: 'Non eseguita', TECHNICAL_ERROR: 'Errore tecnico', ASSESSED: 'Valutazione registrata',
  NOT_REQUIRED_BY_POLICY: 'Non prevista dalla policy', PASS: 'PASS', MISMATCH: 'MISMATCH', UNRESOLVED: 'UNRESOLVED',
  NOT_ESTABLISHED: 'Non stabilita: validazione non superata',
};
function status(value: unknown): string {
  if (!value || typeof value !== 'object') return 'Non registrato';
  const state = (value as Record<string, unknown>).status;
  return typeof state === 'string' ? labels[state] ?? state : 'Non registrato';
}

export default function DocumentaryObservation({ finding, reading }: { finding: DocumentaryFinding; reading?: ReadingFinding }) {
  const [open, setOpen] = useState(false);
  const correspondence = object(finding.checks.correspondence);
  const phenotype = text(object(correspondence.fields).phenotype);
  const scope = object(correspondence.phenotype_scope ?? finding.limitations.phenotype_scope);
  const hasScope = Object.keys(scope).length > 0;
  const population = scope.logical_operator === 'OR' ? 'alternativa: un carattere oppure l’altro'
    : scope.logical_operator === 'AND' ? 'intersezione: entrambi i caratteri'
      : 'rapporto non stabilito';
  const source = finding.source.public_source_identity ?? finding.source.document_id ?? finding.source.paper_id;
  const identifier = typeof source === 'string' ? source : '';
  const url = /^pmid:\d+$/i.test(identifier) ? `https://pubmed.ncbi.nlm.nih.gov/${identifier.split(':')[1]}/`
    : /^(?:pmcid:)?PMC\d+$/i.test(identifier) ? `https://pmc.ncbi.nlm.nih.gov/articles/${identifier.replace(/^pmcid:/i, '').toUpperCase()}/` : null;
  return <Box component="article" sx={{ py: 2, borderTop: `1px solid ${color.hairline}`, overflowWrap: 'anywhere', minWidth: 0 }}>
    <Typography sx={{ fontWeight: 600 }}>{finding.disposition === 'RETAINED_RECORD' ? 'Osservazione conservata' : 'Record escluso'}</Typography>
    <Typography variant="body2" sx={{ color: color.slate }}>{url ? <Link href={url} target="_blank" rel="noopener noreferrer">{identifier}</Link> : identifier || 'Fonte non registrata'}</Typography>
    {finding.quotation && <Typography component="blockquote" sx={{ m: 0, my: 1.5, p: 1.5, bgcolor: color.stone, lineHeight: 1.65 }}>{finding.quotation}</Typography>}
    <ReadingContext reading={reading} />
    {phenotype && <Typography variant="body2">Identità del fenotipo nella fonte: {phenotype === 'CONFIRMED' ? 'corrispondenza confermata' : phenotype === 'NOT_CONFIRMED' ? 'corrispondenza non confermata' : 'corrispondenza non stabilita'}</Typography>}
    {hasScope && <Box component="section" aria-label="Popolazione del fenotipo nella fonte" sx={{ my: 1 }}>
      <Typography variant="body2">Popolazione della fonte: {population}</Typography>
      {text(scope.literal_span) ? <Typography variant="body2">Passaggio letterale sulla popolazione: <Box component="q">{text(scope.literal_span)}</Box></Typography>
        : <Typography variant="body2">Passaggio letterale sulla popolazione: non registrato</Typography>}
      {!reading?.notices.some(notice => notice.code.startsWith('PHENOTYPE_')) && <Typography variant="body2" sx={{ color: color.slate }}>La corrispondenza del fenotipo e la popolazione descritta non stabiliscono un effetto terapeutico specifico per il sottogruppo.</Typography>}
    </Box>}
    <Typography variant="body2">Citazione: {status(finding.checks.quotation)} · Gate: {status(finding.checks.structural)} · Semantica: {status(finding.checks.semantic)}</Typography>
    {Object.keys(finding.observed).length > 0 && <><Typography sx={{ mt: 1.5, fontWeight: 600, fontSize: 14 }}>Contenuto osservato nella fonte</Typography><Typography variant="body2" sx={{ color: color.slate }}>Campi estratti dal Reader, da confrontare con la citazione; non costituiscono una valutazione indipendente.</Typography><ObservedFields observed={finding.observed} /></>}
    {finding.observed.relation_scope != null && finding.observed.intervention_composition == null && <Typography variant="body2" sx={{ color: color.slate }}>Il campo storico relation_scope non stabilisce se il regime sia una monoterapia o una combinazione. Composizioni separate non registrate.</Typography>}
    <Box component="details" onToggle={event => setOpen(event.currentTarget.open)} sx={{ mt: 1.5 }}><summary>Schema originale e tracciabilità</summary>{open && <StructuredValue value={{ evidence_id: finding.evidence_id, target: finding.requested_target, observed: finding.observed, source: finding.source, checks: finding.checks, limitations: finding.limitations }} />}</Box>
    <Typography variant="body2" sx={{ mt: 1, color: color.slate }}>Correttezza scientifica non valutata indipendentemente. Applicabilita clinica non valutata.</Typography>
  </Box>;
}
