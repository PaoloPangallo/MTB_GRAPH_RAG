import { Alert, Box, Button, Link, TextField, Typography } from '@mui/material';
import { useState } from 'react';
import type { CanonicalEntry } from './DossierView';
import { entrySearchText, object, readable, studyGroups, text } from './dossierReading';
import type { DossierReadingGuide } from './contracts.generated';
import StructuredValue from './values/StructuredValue';
import { color, sourceStyle, workspaceOffset } from './tokens';

function RegistrySnapshot({ entry, index }: { entry: CanonicalEntry; index?: number }) {
  const [armQuery, setArmQuery] = useState('');
  const [shownArms, setShownArms] = useState(4);
  const arms = entry.arm_groups ?? [];
  const filteredArms = arms.filter(arm => JSON.stringify([arm.label, arm.description, arm.interventionNames]).toLocaleLowerCase('it').includes(armQuery.toLocaleLowerCase('it')));
  const phases = (Array.isArray(entry.phase) ? entry.phase : [entry.phase]).map(readable).filter(Boolean).join(', ');
  const interventions = [...new Set((entry.interventions ?? []).map(value => text(value) ?? text(object(value).name)).filter(Boolean))];
  return <Box sx={{ mt: 1.5 }}>
    {index !== undefined && <Typography component="h5" sx={{ fontWeight: 600, fontSize: 16, mb: 1 }}>Dati registrati {index + 1}: {entry.title ?? 'Titolo non disponibile'}</Typography>}
    <Typography>Stato del registro: {readable(entry.status) ?? 'Non registrato'} · {phases || 'Fase non registrata'}</Typography>
    <Box component={arms.length ? 'details' : 'div'} sx={{ mt: 1 }}>
      {!!arms.length && <summary>Condizioni e interventi dello studio complessivo</summary>}
      <Typography sx={{ mt: 1 }}>Condizioni dello studio: {(entry.conditions ?? []).filter(item => typeof item === 'string').join(', ') || 'Non registrate'}</Typography>
      <Typography sx={{ mt: 1 }}>Interventi dello studio complessivo: {interventions.join(', ') || 'Non registrati'}. L’elenco non attribuisce i trattamenti a una specifica popolazione.</Typography>
    </Box>
    {!entry.arm_groups?.length ? <Typography sx={{ mt: 1 }}>Bracci non disponibili: associazione fra popolazione e intervento non determinata.</Typography>
      : <Box component="section" aria-label="Bracci dello studio" sx={{ mt: 2 }}>
        {arms.length > 4 && <TextField label="Cerca nei bracci dello studio" value={armQuery} size="small" fullWidth
          onChange={event => { setArmQuery(event.target.value); setShownArms(4); }} sx={{ mb: 1 }} />}
        <Typography variant="body2" role="status">{filteredArms.length} bracci{armQuery ? ' corrispondenti alla ricerca' : ' registrati'}; mostrati {Math.min(shownArms, filteredArms.length)}.</Typography>
        {filteredArms.slice(0, shownArms).map((arm, index) => <Box component="article" key={index} sx={{ py: 1.5, borderTop: `1px solid ${color.hairline}`, minWidth: 0 }}>
          <Typography component="h5" sx={{ fontSize: 16, fontWeight: 600 }}>{text(arm.label) ?? `Braccio senza etichetta (${index + 1})`}</Typography>
          <Typography sx={{ mt: 0.5, whiteSpace: 'pre-wrap', maxWidth: '75ch' }}>{text(arm.description) ?? 'Popolazione o descrizione del braccio non riportata'}</Typography>
          <Typography sx={{ mt: 0.5 }}>Interventi di questo braccio: {Array.isArray(arm.interventionNames) ? arm.interventionNames.filter(value => typeof value === 'string').join(', ') || 'Non riportati' : 'Non riportati'}</Typography>
        </Box>)}
        {shownArms < filteredArms.length && <Button onClick={() => setShownArms(count => count + 4)}>Mostra altri bracci ({filteredArms.length - shownArms})</Button>}
      </Box>}
  </Box>;
}

function Study({ entries, recordedSnapshots }: { entries: CanonicalEntry[]; recordedSnapshots?: CanonicalEntry[] }) {
  const [open, setOpen] = useState(false);
  const entry = entries[0];
  const nct = entry.nct_id?.replace(/^nct:/i, '').toUpperCase();
  const validNct = nct && /^NCT\d{8}$/.test(nct);
  const snapshots = recordedSnapshots ?? [...new Map(entries.map(item => [JSON.stringify([item.title, item.status, item.phase, item.conditions, item.interventions, item.arm_groups, item.arm_group_status, item.trial_structure_provenance, item.trial_resolution_status]), item])).values()];
  return <Box component="article" sx={{ borderTop: `1px solid ${color.hairline}`, py: 2.5, overflowWrap: 'anywhere' }}>
    <Typography component="h4" sx={{ fontWeight: 600, fontSize: 17 }}>{entry.title ?? 'Titolo dello studio non disponibile'}</Typography>
    {validNct ? <Link href={`https://clinicaltrials.gov/study/${nct}`} target="_blank" rel="noopener noreferrer">{nct}</Link> : <Typography>Identificativo NCT non disponibile</Typography>}
    {snapshots.length > 1 && <Alert severity="warning" sx={{ mt: 1 }}>Dati di registro discordanti fra le associazioni: riportati separatamente, senza fondere i bracci.</Alert>}
    {snapshots.map((snapshot, index) => <RegistrySnapshot key={index} entry={snapshot} index={snapshots.length > 1 ? index : undefined} />)}
    <Typography variant="body2" sx={{ mt: 1 }}>Eleggibilità del paziente non valutata</Typography>
    <Alert severity="info" sx={{ mt: 1.5 }}>Associazione a trial: non costituisce prova di efficacia terapeutica né valutazione completa dell’eleggibilità del paziente. Lo stato del registro non dimostra disponibilità locale.</Alert>
    <Box component="details" onToggle={event => setOpen(event.currentTarget.open)} sx={{ mt: 1.5 }}>
      <summary>Associazioni nel grafo ({entries.length})</summary>
      {open && entries.map(item => <Box key={item.candidate_id} sx={{ py: 1.5, borderBottom: `1px solid ${color.hairline}` }}>
        <StructuredValue value={item} />
      </Box>)}
    </Box>
  </Box>;
}

export default function TrialStudies({ entries, searching = false, query = '', guide }: { entries: CanonicalEntry[]; searching?: boolean; query?: string; guide?: DossierReadingGuide | null }) {
  const [shown, setShown] = useState(8);
  const allGroups = guide && guide.trial_association_count === entries.length
    ? guide.trial_groups.map(group => ({ entries: group.entry_indexes.map(index => entries[index]), snapshots: group.snapshot_indexes.map(index => entries[index]) }))
    : studyGroups(entries).map(group => ({ entries: group, snapshots: undefined }));
  // Search after grouping: one matching association must not hide conflicting snapshots.
  const groups = allGroups.filter(group => group.entries.some(entry => entrySearchText(entry).includes(query.trim().toLocaleLowerCase('it'))));
  const identified = groups.filter(group => /^(?:nct:)?NCT\d{8}$/i.test(group.entries[0].nct_id ?? '')).length;
  const associationCount = groups.reduce((sum, group) => sum + group.entries.length, 0);
  return <Box component="section" id="dossier-trial" sx={{ mb: 4, minWidth: 0, scrollMarginTop: `${workspaceOffset}px` }}>
    <Typography component="h3" sx={{ fontSize: 20, fontWeight: 600, p: 1.5, color: sourceStyle.trial.fg, bgcolor: sourceStyle.trial.bg }}>Studi clinici</Typography>
    <Typography sx={{ my: 1 }}>{identified} studi distinti / {associationCount} associazioni nel grafo</Typography>
    {groups.length > identified && <Typography variant="body2">{groups.length - identified} associazioni senza identificativo di studio verificabile, mantenute separate.</Typography>}
    {!groups.length && <Typography>{searching ? 'Nessuna relazione corrisponde alla ricerca.' : 'Nessuna relazione in questo percorso.'}</Typography>}
    {groups.slice(0, shown).map(group => <Study key={group.entries[0].candidate_id} entries={group.entries} recordedSnapshots={group.snapshots} />)}
    {shown < groups.length && <Button onClick={() => setShown(count => count + 8)}>Mostra altri studi ({groups.length - shown})</Button>}
  </Box>;
}
