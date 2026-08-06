/**
 * Ingresso della pipeline: testo clinico libero.
 *
 * Il percorso principale parte da qui e non da campi strutturati. Un modulo con
 * `gene`, `alteration`, `disease` e `direction` scavalcherebbe il CaseContext
 * Parser: il relatore vedrebbe un CaseContext corretto senza che nessun modello
 * lo abbia estratto, e lo stage 2 diventerebbe una formalità. I campi
 * strutturati restano visibili **come risultato** del parser, mai come input.
 *
 * La modalità di esecuzione si **sceglie**, non si deduce.
 *
 * Prima veniva inferita dal testo: se coincideva con un caso dimostrativo la run
 * diventava replay, altrimenti live. Il criterio era comprensibile ma faceva sì
 * che la modalità dipendesse da un dettaglio dell'input invece che da una
 * decisione, e che non esistesse alcun modo di eseguire dal vivo proprio i casi
 * per cui il confronto con gli artefatti registrati è più interessante.
 *
 * - `LIVE` esegue ogni stage ora, cache documentale e chiamate al modello
 *   comprese. Richiede che la cache sia disponibile: se non lo è, la run
 *   fallisce dicendolo e **non** ripiega sul replay.
 * - `REPLAY` rigioca gli artefatti registrati del pilot, che sono risposte reali
 *   del modello, non finzioni. Disponibile solo per i casi che ne hanno.
 */

import { useMemo, useState } from 'react';
import { Alert, Box, Button, Chip, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { color, font, radius } from './tokens';
import type { DemoCase, RequestableMode } from './types';

export interface RunRequest {
  demo_case_key?: string;
  clinical_text?: string;
  case_id?: string;
  execution_mode: RequestableMode;
}

interface CaseInputPanelProps {
  cases: DemoCase[];
  busy: boolean;
  onRun: (request: RunRequest) => void;
  /** Dal backend: se la cache documentale manca, LIVE non è eseguibile. */
  liveAvailable?: boolean;
}

/** Identificativo di una run su testo inedito. Leggibile, e ordinabile nel tempo. */
function freeTextCaseId(): string {
  const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
  return `FREETEXT-${stamp}`;
}

function caseLabel(caseId: string): string {
  return caseId.replace(/^CASE-\d+-/, '').replace(/-/g, ' ');
}

export default function CaseInputPanel({
  cases, busy, onRun, liveAvailable = true,
}: CaseInputPanelProps) {
  const [text, setText] = useState('');
  const [touchedCaseId, setTouchedCaseId] = useState<string | null>(null);
  const [mode, setMode] = useState<RequestableMode>('LIVE');

  const trimmed = text.trim();

  // Il caso dimostrativo vale solo finché il testo è quello: modificato il
  // testo, non esistono artefatti registrati corrispondenti da rigiocare.
  const matchingDemo = useMemo(
    () => cases.find((demo) => demo.clinical_text.trim() === trimmed) ?? null,
    [cases, trimmed],
  );

  const replayAvailable = Boolean(matchingDemo?.frozen_artifacts_available);
  const modeUsable = mode === 'LIVE' ? liveAvailable : replayAvailable;
  const canRun = trimmed.length > 0 && !busy && modeUsable;

  const submit = () => {
    if (!canRun) return;
    if (matchingDemo) {
      onRun({ demo_case_key: matchingDemo.case_id, execution_mode: mode });
      return;
    }
    onRun({ clinical_text: trimmed, case_id: freeTextCaseId(), execution_mode: mode });
  };

  return (
    <Box sx={{ mt: 5 }}>
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
          setTouchedCaseId(null);
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

        {/* La modalità è un interruttore, non una conseguenza del testo. */}
        <Stack direction="row" spacing={0.75} role="group" aria-label="Modalità di esecuzione">
          {(['LIVE', 'REPLAY'] as const).map((option) => {
            const usable = option === 'LIVE' ? liveAvailable : replayAvailable;
            return (
              <Tooltip
                key={option}
                title={
                  option === 'LIVE'
                    ? (liveAvailable
                      ? 'Ogni stage viene eseguito ora: documenti letti dalla cache autorizzata e chiamate reali al modello.'
                      : 'Cache documentale non disponibile: una run LIVE fallirebbe dichiarandolo, senza ripiegare sul replay.')
                    : (replayAvailable
                      ? 'Rigioca gli artefatti registrati del pilot: risposte reali del modello, non rieseguite ora.'
                      : 'Nessun artefatto registrato per questo testo: non c’è nulla da rigiocare.')
                }
              >
                <Chip
                  label={option}
                  size="small"
                  onClick={() => setMode(option)}
                  aria-pressed={mode === option}
                  data-testid={`mode-${option.toLowerCase()}`}
                  sx={{
                    height: 24, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
                    cursor: 'pointer', borderRadius: '6px',
                    opacity: usable ? 1 : 0.45,
                    backgroundColor: mode === option ? color.ink : color.stone,
                    color: mode === option ? '#fff' : color.body,
                  }}
                />
              </Tooltip>
            );
          })}
        </Stack>
      </Stack>

      {mode === 'LIVE' && !liveAvailable && (
        <Alert severity="warning" sx={{ mt: 2, borderRadius: '8px', fontSize: 13 }}>
          La cache documentale non è disponibile: una run LIVE si fermerebbe allo stage 6
          con <code>DOCUMENT_CACHE_UNAVAILABLE</code>. Non viene sostituita da una run
          registrata — configura <code>RESEARCH_DOCUMENT_CACHE_PATH</code>, oppure scegli
          REPLAY in modo esplicito.
        </Alert>
      )}

      {mode === 'REPLAY' && trimmed.length > 0 && !replayAvailable && (
        <Alert severity="info" sx={{ mt: 2, borderRadius: '8px', fontSize: 13 }}>
          Nessun artefatto registrato corrisponde a questo testo. Una run REPLAY non
          avrebbe nulla da rigiocare: scegli LIVE, oppure uno dei casi dimostrativi.
        </Alert>
      )}

      {mode === 'REPLAY' && replayAvailable && (
        <Alert severity="info" sx={{ mt: 2, borderRadius: '8px', fontSize: 13 }}>
          Gli stage 2, 8, 9 e 10 rigiocheranno gli artefatti registrati al commit
          <code> 6ee64c5</code>. Sono risposte reali del modello, non finzioni, ma non
          vengono prodotte ora: la run sarà etichettata REPLAY e non potrà essere
          presentata come live.
        </Alert>
      )}

      <Box sx={{ mt: 3.5 }}>
        <Typography sx={{
          fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
          textTransform: 'uppercase', color: color.muted, mb: 1.5,
        }}>
          Casi dimostrativi — compilano il testo qui sopra
        </Typography>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
          {cases.map((demo) => (
            <Tooltip key={demo.case_id} title={demo.expected_result ?? ''}>
              <Chip
                label={caseLabel(demo.case_id)}
                onClick={() => {
                  setText(demo.clinical_text);
                  setTouchedCaseId(demo.case_id);
                }}
                disabled={busy}
                sx={{
                  fontFamily: font.body, fontSize: 13, cursor: 'pointer',
                  borderRadius: `${radius.pill}px`, height: 30,
                  backgroundColor: touchedCaseId === demo.case_id ? color.ink : color.stone,
                  color: touchedCaseId === demo.case_id ? '#fff' : color.body,
                  '&:hover': { backgroundColor: touchedCaseId === demo.case_id ? '#000' : color.hairline },
                }}
              />
            </Tooltip>
          ))}
          {cases.length === 0 && (
            <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.muted }}>
              Caricamento dei casi…
            </Typography>
          )}
        </Stack>
      </Box>
    </Box>
  );
}
