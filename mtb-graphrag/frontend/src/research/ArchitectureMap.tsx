import { Box, Button, Stack, Typography } from '@mui/material';
import AccountTreeOutlined from '@mui/icons-material/AccountTreeOutlined';
import ArticleOutlined from '@mui/icons-material/ArticleOutlined';
import ScienceOutlined from '@mui/icons-material/ScienceOutlined';
import HubOutlined from '@mui/icons-material/HubOutlined';
import ArrowDownward from '@mui/icons-material/ArrowDownward';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import ErrorOutline from '@mui/icons-material/ErrorOutlined';
import PendingOutlined from '@mui/icons-material/PendingOutlined';
import type { PipelineStage } from './types';
import { color, sourceStyle, stageStatusStyle } from './tokens';

interface Props {
  stages: PipelineStage[];
  selectedStageId: string | null;
  onSelect: (stageId: string) => void;
}

export default function ArchitectureMap({ stages, selectedStageId, onSelect }: Props) {
  const node = (id: string, label: string) => {
    const stage = stages.find(item => item.stage_id === id);
    const status = stage ? stageStatusStyle[stage.status] : null;
    const StatusIcon = stage?.status === 'SUCCEEDED' ? CheckCircleOutlined : stage?.status === 'FAILED' ? ErrorOutline : PendingOutlined;
    return <Button key={id} disabled={!stage} onClick={() => {
      onSelect(id);
      document.getElementById('stage-inspector')?.scrollIntoView({ block: 'start' });
    }} aria-pressed={selectedStageId === id} sx={{ textTransform: 'none', flexDirection: 'column', alignItems: 'flex-start', textAlign: 'left', px: 1.5, py: 1.5, minWidth: 0, flex: 1, border: `1px solid ${selectedStageId === id ? color.deepGreen : color.hairline}`, borderRadius: '8px', color: color.ink, bgcolor: selectedStageId === id ? '#eff6f3' : color.canvas, '&:hover': { bgcolor: '#f4f6f5' }, '&:focus-visible': { outline: `2px solid ${color.focus}` } }}>
      <Typography component="span" sx={{ fontSize: 14, fontWeight: 600 }}>{label}</Typography>
      <Stack component="span" direction="row" spacing={0.5} sx={{ mt: 0.75, alignItems: 'center', color: status?.fg ?? color.slate }}><StatusIcon sx={{ fontSize: 15 }} /><Typography component="span" sx={{ fontSize: 12 }}>{status?.label ?? 'Non ancora disponibile'}</Typography></Stack>
    </Button>;
  };
  const arrow = <ArrowDownward aria-hidden sx={{ display: 'block', mx: 'auto', my: 1, color: color.muted, fontSize: 20 }} />;
  return <Box component="section" aria-label="Architettura della pipeline" sx={{ mt: 4, py: 3, borderTop: `1px solid ${color.hairline}`, borderBottom: `1px solid ${color.hairline}` }}>
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}><AccountTreeOutlined /><Typography component="h2" sx={{ fontSize: 22, fontWeight: 600 }}>Come si costruisce il dossier</Typography></Stack>
    <Typography sx={{ color: color.slate, fontSize: 14, mb: 2, maxWidth: '72ch' }}>Il grafo propone le relazioni. Ogni percorso conserva il proprio tipo di fonte e di verifica. Seleziona un passaggio per ispezionarlo.</Typography>
    <Stack direction={{ xs: 'column', lg: 'row' }} spacing={1} sx={{ alignItems: 'stretch' }}>
      {node('stage_1_case_input', 'Caso')}{node('stage_2_casecontext_parser', 'Estrazione')}{node('stage_3_casecontext_match', 'Riscontro nel testo')}{node('stage_3b_pre_retrieval_eligibility_gate', 'Gate di ammissione')}{node('stage_4_retrieval_plan', 'Piano')}{node('stage_5_kg_retrieval', 'Relazioni dal grafo')}
    </Stack>
    {arrow}
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' }, gap: 3, borderTop: `1px solid ${color.hairline}`, pt: 2 }}>
      <Box sx={{ bgcolor: sourceStyle.paper.bg, color: sourceStyle.paper.fg, p: 2, borderRadius: '8px' }}><Stack direction="row" spacing={1}><ArticleOutlined /><Typography component="h3" sx={{ fontWeight: 600 }}>PAPER · Pubblicazioni</Typography></Stack>
        <Typography sx={{ fontSize: 13, color: color.slate, my: 1 }}>Documento → passaggi → relazione osservata → citazione autenticata e controlli di corrispondenza registrati.</Typography>
      </Box>
      <Box sx={{ bgcolor: sourceStyle.trial.bg, color: sourceStyle.trial.fg, p: 2, borderRadius: '8px' }}><Stack direction="row" spacing={1}><ScienceOutlined /><Typography component="h3" sx={{ fontWeight: 600 }}>TRIAL · Studi clinici</Typography></Stack>
        <Typography sx={{ fontSize: 13, color: color.slate, my: 1 }}>Record del trial e osservazioni sul registro. L’associazione non dimostra efficacia né eleggibilità del paziente.</Typography>
        <Typography sx={{ fontSize: 13 }}>Condivide gli stage documentali con PAPER. Gli stati sono aggregati per stage.</Typography>
      </Box>
      <Box sx={{ bgcolor: sourceStyle.kg.bg, color: sourceStyle.kg.fg, p: 2, borderRadius: '8px' }}><Stack direction="row" spacing={1}><HubOutlined /><Typography component="h3" sx={{ fontWeight: 600 }}>KG_ONLY · Relazioni del grafo</Typography></Stack>
        <Typography sx={{ fontSize: 13, color: color.slate, my: 1 }}>Provenienza del Knowledge Graph, senza citazione documentale autenticata nella run. Non attraversa il reader documentale.</Typography>
      </Box>
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 2fr) minmax(0, 1fr)' }, gap: 3, mt: 2 }}>
      <Box sx={{ pt: 2, borderTop: `1px solid ${color.hairline}` }}>
        <Typography sx={{ fontWeight: 600, fontSize: 14, mb: 1.5 }}>Verifica delle fonti · PAPER e TRIAL</Typography>
        <Stack spacing={1}>
          {node('stage_6_document_resolution', 'Risoluzione delle fonti')}{node('stage_7_source_units', 'Passaggi documentali')}{node('stage_8_paper_selection', 'Selezione')}{node('stage_9_paper_context_enricher', 'Reader')}{node('stage_10_enrichment_validation', 'Verifica documentale')}
        </Stack>
      </Box>
      <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', borderTop: `1px solid ${color.hairline}`, py: 3, px: 2 }}>
        <HubOutlined sx={{ fontSize: 32, color: color.slate }} /><Typography sx={{ fontSize: 14, mt: 1 }}>Provenienza del grafo</Typography>
        <Typography sx={{ fontSize: 13, color: color.slate, mt: 1, maxWidth: '30ch' }}>KG_ONLY raggiunge il dossier senza trasformarsi in evidenza documentale.</Typography>
        <ArrowDownward sx={{ mt: 2, color: color.slate }} />
      </Box>
    </Box>
    {arrow}
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
      {node('stage_11_deterministic_gates', 'Controlli deterministici')}{node('stage_12_status', 'Classificazione')}{node('stage_13_dossier', 'Dossier canonico')}
    </Stack>
    {arrow}
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>{node('stage_14_narrator', 'Sintesi generata')}{node('stage_15_narrative_verifier', 'Verifica della narrazione')}</Stack>
    <Typography sx={{ textAlign: 'center', fontSize: 13, color: color.slate, mt: 1 }}>La narrazione accettata spiega il dossier; non modifica gli esiti.</Typography>
  </Box>;
}
