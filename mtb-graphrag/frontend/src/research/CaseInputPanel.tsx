import PlayArrowOutlined from '@mui/icons-material/PlayArrowOutlined';
/**
 * Ingresso della pipeline: testo clinico libero.
 *
 * Il percorso principale parte da qui e non da campi strutturati. Un modulo con
 * `gene`, `alteration`, `disease` e `direction` scavalcherebbe il CaseContext
 * Parser: il relatore vedrebbe un CaseContext corretto senza che nessun modello
 * lo abbia estratto, e lo stage 2 diventerebbe una formalità. I campi
 * strutturati restano visibili **come risultato** del parser, mai come input.
 *
 * **Non c'è una modalità da scegliere.** Qui esisteva un interruttore
 * LIVE/REPLAY, e prima ancora la modalità veniva dedotta dal testo. Entrambe le
 * soluzioni chiedevano al clinico di sapere cosa fossero un artefatto congelato
 * e un bundle, per decidere qualcosa che non gli compete: il sistema esegue la
 * pipeline, oppure dichiara perché non può. Il replay degli esperimenti storici
 * resta, ma è infrastruttura di ricerca e non passa da questa pagina.
 */

import { useMemo, useState } from 'react';
import { Alert, Box, Button, Chip, ListSubheader, MenuItem, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { color, font, radius } from './tokens';
import type { DemoCase } from './types';
import observedCatalog from './observedDemoCases.json';

export interface ObservedCase {
  case_id: string;
  title: string;
  clinical_text: string;
  group: 'PAPER' | 'TRIAL' | 'KG';
  counts: { PAPER: number; TRIAL: number; KG: number };
  status: string;
  run_id: string;
  observed_at: string;
  elapsed_seconds?: number;
  behavior_description?: string;
  presentation_mode: string;
}

export interface RunRequest {
  demo_case_key?: string;
  clinical_text?: string;
  case_id?: string;
}

interface CaseInputPanelProps {
  cases: DemoCase[];
  observedCases?: ObservedCase[];
  busy: boolean;
  onRun: (request: RunRequest) => void;
  /** Disponibilità documentale: il ramo KG_ONLY non richiede la cache. */
  documentCacheAvailable?: boolean;
}

/** Identificativo di una run su testo inedito. Leggibile, e ordinabile nel tempo. */
function freeTextCaseId(): string {
  const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
  return `FREETEXT-${stamp}`;
}

function caseLabel(caseId: string): string {
  const labels: Record<string, string> = {
    'CASE-1-therapy-evaluation-strong-match': 'Colon-retto · KRAS G12D — valutazione di panitumumab',
    'CASE-2-therapy-discovery': 'Colon-retto · BRAF V600E — ricerca di opzioni',
    'CASE-3-partial-incomplete-context': 'Colon-retto · MSI — contesto molecolare incompleto',
    'CASE-4-contradicted-or-resistance': 'Polmone · FGFR1 — riscontro su infigratinib',
    'CASE-5-casecontext-mismatch-no-match': 'Caso di controllo — biomarcatore senza corrispondenze',
  };
  return labels[caseId] ?? caseId.replace(/^CASE-\d+-/, '').replace(/-/g, ' ');
}

const BRANCH_EXAMPLES = [
  { branch: 'PAPER', description: 'Documento → Source Unit → Reader → verifica della relazione. Una citazione autentica richiede ancora controlli di corrispondenza.' },
  { branch: 'TRIAL', description: 'Record dello studio e contesto di arruolamento. Nessuna inferenza di efficacia o eleggibilità del paziente.' },
  { branch: 'KG ONLY', description: 'Relazione conservata con provenienza del grafo, senza attribuirle supporto documentale.' },
] as const;

export default function CaseInputPanel({
  cases, busy, onRun, documentCacheAvailable = true,
  observedCases = observedCatalog.cases as ObservedCase[],
}: CaseInputPanelProps) {
  const [text, setText] = useState('');

  const trimmed = text.trim();
  const examples = observedCases.length ? observedCases : cases;
  const matchingExample = examples.find(demo => demo.clinical_text.trim() === trimmed);
  const observed = observedCases.find(demo => demo.clinical_text.trim() === trimmed);

  // Un caso dimostrativo compila il testo; se il testo resta quello, la run
  // parte dal caso e non da un identificativo inventato. È una comodità di
  // identificazione, non un percorso di esecuzione diverso.
  const matchingDemo = useMemo(
    () => cases.find((demo) => demo.clinical_text.trim() === trimmed) ?? null,
    [cases, trimmed],
  );

  const canRun = trimmed.length > 0 && !busy;

  const submit = () => {
    if (!canRun) return;
    if (matchingDemo) {
      onRun({ demo_case_key: matchingDemo.case_id });
      return;
    }
    onRun({ clinical_text: trimmed, case_id: freeTextCaseId() });
  };

  return (
    <Box sx={{ mt: 5 }}>
          <TextField
            select fullWidth label="Scegli un caso di esempio"
            value={matchingExample?.case_id ?? ''} disabled={busy || examples.length === 0}
            helperText="Esempi sintetici: la selezione compila il testo, poi puoi modificarlo o eseguire la pipeline."
            onChange={(event) => {
              const selected = examples.find(demo => demo.case_id === event.target.value);
              if (selected) setText(selected.clinical_text);
            }}
            sx={{ mb: 2, '& .MuiSelect-select': { whiteSpace: 'normal' } }}
          >
            <MenuItem value="" disabled>Seleziona un esempio</MenuItem>
            {observedCases.length ? (['PAPER', 'TRIAL', 'KG'] as const).flatMap(group => [
              <ListSubheader key={`group-${group}`}>{group === 'PAPER' ? 'Con pubblicazioni nel dossier' : group === 'TRIAL' ? 'Con studi clinici nel dossier' : 'Solo relazioni del Knowledge Graph'}</ListSubheader>,
              ...observedCases.filter(demo => demo.group === group).map(demo => <MenuItem key={demo.case_id} value={demo.case_id} sx={{ whiteSpace: 'normal' }}>{demo.title}</MenuItem>),
            ]) : [...cases].sort((a, b) => Number(b.case_id === 'CASE-2-therapy-discovery') - Number(a.case_id === 'CASE-2-therapy-discovery')).map(demo => (
              <MenuItem key={demo.case_id} value={demo.case_id} sx={{ whiteSpace: 'normal', maxWidth: '100%' }}>{caseLabel(demo.case_id)}</MenuItem>
            ))}
          </TextField>
          {observed && <Box sx={{ width: '100%', mb: 2 }}>
            <Typography sx={{ fontSize: 13, fontWeight: 600 }}>Ultima esecuzione osservata · {new Date(observed.observed_at).toLocaleString('it-IT')}</Typography>
            <Typography sx={{ fontSize: 13, color: color.slate }}>{observed.counts.PAPER} relazioni da pubblicazioni · {observed.counts.TRIAL} associazioni a studi clinici · {observed.counts.KG} relazioni KG</Typography>
            {observed.behavior_description && <Typography sx={{ fontSize: 13, my: 0.5 }}>{observed.behavior_description}</Typography>}
            <Typography sx={{ fontSize: 12, color: color.slate }}>{observed.status === 'COMPLETED' ? 'Run completata' : 'Run completata con riserve'} · {observed.presentation_mode === 'VERIFIED_NARRATIVE' ? 'Narrazione verificata' : observed.presentation_mode === 'DETERMINISTIC_NARRATIVE_FALLBACK' ? 'Sintesi dal dossier' : 'Dossier strutturato'}. Esito storico su caso sintetico: una nuova esecuzione può differire.</Typography>
            {observed.elapsed_seconds !== undefined && <Typography sx={{ fontSize: 12, color: color.slate }}>Durata osservata: {Math.round(observed.elapsed_seconds)} secondi.</Typography>}
          </Box>}

      <Typography sx={{
        fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
        textTransform: 'uppercase', color: color.muted, mb: 1.5,
      }}>
        Testo clinico
      </Typography>

      <TextField
        multiline
        minRows={4}
        fullWidth
        value={text}
        onChange={(event) => {
          setText(event.target.value);
        }}
        placeholder={
          'Paziente con adenocarcinoma polmonare e mutazione EGFR L858R. '
          + 'Si vuole valutare osimertinib.'
        }
        slotProps={{ htmlInput: { 'aria-label': 'Testo clinico in linguaggio libero' } }}
        sx={{
          '& .MuiOutlinedInput-root': {
            fontFamily: font.body, fontSize: 15, borderRadius: `${radius.md}px`,
            backgroundColor: '#fff',
          },
        }}
      />

      <Typography sx={{ mt: 1, fontFamily: font.body, fontSize: 12, color: color.slate }}>
        Il CaseContext non si compila: viene estratto da questo testo dal parser,
        e ogni campo estratto viene poi riconfrontato con il testo stesso.
      </Typography>

      <Stack direction="row" spacing={1.5} sx={{ mt: 2, alignItems: 'center', flexWrap: 'wrap' }}>
        <Button
          onClick={submit}
          disabled={!canRun}
          data-testid="run-pipeline"
          startIcon={<PlayArrowOutlined />}
          sx={{
            fontFamily: font.body, fontSize: 14, textTransform: 'none',
            borderRadius: `${radius.pill}px`, px: 3, py: 1,
            backgroundColor: color.ink, color: '#fff',
            '&:hover': { backgroundColor: '#000' },
            '&.Mui-disabled': { backgroundColor: color.hairline, color: color.muted },
          }}
        >
          {busy ? 'Avvio…' : 'Esegui la pipeline'}
        </Button>
      </Stack>

      {/* L'indisponibilità della cache è un fatto da dire, non un motivo per
          offrire un secondo percorso: non ne esiste uno. */}
      {!documentCacheAvailable && (
        <Alert severity="warning" data-testid="document-cache-unavailable"
               sx={{ mt: 2, borderRadius: '8px', fontSize: 13 }}>
          La cache documentale non è disponibile. PAPER e TRIAL richiedono il runtime
          documentale; KG_ONLY resta eseguibile. Il backend decide il percorso dopo
          la verifica del caso e dichiara le eventuali fonti non disponibili.
        </Alert>
      )}

      <Box sx={{ mt: 3.5 }}>
        <Typography sx={{
          fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
          textTransform: 'uppercase', color: color.muted, mb: 1.5,
        }}>
          Percorsi delle fonti
        </Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
          {BRANCH_EXAMPLES.map((example) => (
            <Tooltip
              key={example.branch}
              title={(
                <Box sx={{ maxWidth: 360, py: 0.25 }}>
                  <Typography sx={{ fontFamily: font.body, fontSize: 12, fontWeight: 600 }}>
                    {example.description}
                  </Typography>
                </Box>
              )}
            >
              <Chip
                label={example.branch}
                variant="outlined"
                sx={{
                  fontFamily: font.mono, fontSize: 11, borderRadius: `${radius.pill}px`, height: 30,
                  borderColor: color.hairline, color: color.body,
                }}
              />
            </Tooltip>
          ))}
          {examples.length === 0 && (
            <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.muted }}>
              Caricamento dei casi…
            </Typography>
          )}
        </Stack>
      </Box>
    </Box>
  );
}
