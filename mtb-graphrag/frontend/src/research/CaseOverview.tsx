import { Box, Link, Stack, Typography } from '@mui/material';
import ArticleOutlined from '@mui/icons-material/ArticleOutlined';
import ScienceOutlined from '@mui/icons-material/ScienceOutlined';
import HubOutlined from '@mui/icons-material/HubOutlined';
import SubjectOutlined from '@mui/icons-material/SubjectOutlined';
import WarningAmberOutlined from '@mui/icons-material/WarningAmberOutlined';
import type { Dossier } from './DossierView';
import { color, sourceStyle } from './tokens';
import { studyGroups } from './dossierReading';

/** Counts describe canonical entries, never efficacy, relevance or eligibility. */
export default function CaseOverview({ dossier, onNavigate }: { dossier: Dossier; onNavigate?: (anchor: string) => void }) {
  if (!dossier.paper_evidence && !dossier.clinical_trials && !dossier.kg_only_relations) return null;
  const studyCount = studyGroups(dossier.clinical_trials ?? []).filter(group => /^(?:nct:)?NCT\d{8}$/i.test(group[0].nct_id ?? '')).length;
  const sources = [
    { kind: 'paper' as const, entries: dossier.paper_evidence, Icon: ArticleOutlined },
    { kind: 'trial' as const, entries: dossier.clinical_trials, Icon: ScienceOutlined },
    { kind: 'kg' as const, entries: dossier.kg_only_relations, Icon: HubOutlined },
  ];
  const follow = (anchor: string) => (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (onNavigate) { event.preventDefault(); onNavigate(anchor); }
  };
  return <Box component="nav" aria-label="Riepilogo e navigazione del dossier" sx={{ my: 2, borderBlock: `1px solid ${color.hairline}`, py: 1.5 }}>
    <Typography component="h2" sx={{ fontSize: 18, fontWeight: 600, mb: 1.5 }}>Il dossier a colpo d’occhio</Typography>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' }, gap: 1 }}>
      {sources.map(({ kind, entries, Icon }) => <Link key={kind} href={`#dossier-${kind}`} onClick={follow(`dossier-${kind}`)} aria-label={`${sourceStyle[kind].label} ${kind === 'trial' ? studyCount : entries?.length ?? 0}`} underline="none" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 1.5, borderRadius: '8px', color: sourceStyle[kind].fg, bgcolor: sourceStyle[kind].bg, '&:hover': { textDecoration: 'underline' }, '&:focus-visible': { outline: `2px solid ${color.focus}`, outlineOffset: 2 } }}>
        <Icon /><Typography component="span" sx={{ flex: 1, fontWeight: 600 }}>{sourceStyle[kind].label}</Typography><Typography component="span" sx={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{kind === 'trial' ? studyCount : entries?.length ?? 0}</Typography>
      </Link>)}
    </Box>
    <Typography sx={{ fontSize: 12, color: color.slate, mt: 1 }}>Pubblicazioni e Knowledge Graph: conteggi delle relazioni nel dossier, non misure di efficacia clinica. Studi identificati: {studyCount} / associazioni a trial: {dossier.clinical_trials?.length ?? 0}.</Typography>
    <Stack direction="row" sx={{ gap: 2, flexWrap: 'wrap', mt: 2 }}>
      <Link href="#case-narrative" onClick={follow('case-narrative')} sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'center' }}><SubjectOutlined fontSize="small" />Sintesi narrativa</Link>
      <Link href="#dossier-case" onClick={follow('dossier-case')}>Caso estratto</Link>
      <Link href="#dossier-limits" onClick={follow('dossier-limits')} sx={{ display: 'inline-flex', gap: 0.75, alignItems: 'center' }}><WarningAmberOutlined fontSize="small" />Limiti del dossier</Link>
    </Stack>
  </Box>;
}
