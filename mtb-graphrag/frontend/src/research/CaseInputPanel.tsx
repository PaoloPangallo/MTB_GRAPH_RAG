/**
 * Ingresso della pipeline: testo clinico libero.
 *
 * Il percorso principale parte da qui e non da campi strutturati. Un modulo con
 * `gene`, `alteration`, `disease` e `direction` scavalcherebbe il CaseContext
 * Parser: il relatore vedrebbe un CaseContext corretto senza che nessun modello
 * lo abbia estratto, e lo stage 2 diventerebbe una formalità. I campi
 * strutturati restano visibili **come risultato** del parser, mai come input.
 *
 * Due modalità di esecuzione, dichiarate prima di premere:
 *
 * - un caso dimostrativo non modificato riproduce gli artefatti congelati del
 *   pilot per gli stage documentali, che sono risposte reali del modello
 *   registrate, non finzioni;
 * - un testo qualunque avvia una run LIVE, in cui il parser viene davvero
 *   chiamato.
 *
 * Dirlo prima conta: le due producono trace diverse, e scoprirlo dopo
 * renderebbe ambiguo ciò che si sta guardando.
 */

import { useMemo, useState } from 'react';
import { Alert, Box, Button, Chip, Stack, TextField, Tooltip, Typography } from '@mui/material';
import { color, font, radius } from './tokens';
import type { DemoCase } from './types';

export interface RunRequest {
  demo_case_key?: string;
  clinical_text?: string;
  case_id?: string;
}

interface CaseInputPanelProps {
  cases: DemoCase[];
  busy: boolean;
  onRun: (request: RunRequest) => void;
}

/** Identificativo di una run su testo inedito. Leggibile, e ordinabile nel tempo. */
function freeTextCaseId(): string {
  const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 15);
  return `FREETEXT-${stamp}`;
}

function caseLabel(caseId: string): string {
  return caseId.replace(/^CASE-\d+-/, '').replace(/-/g, ' ');
}

export default function CaseInputPanel({ cases, busy, onRun }: CaseInputPanelProps) {
  const [text, setText] = useState('');
  const [touchedCaseId, setTouchedCaseId] = useState<string | null>(null);

  const trimmed = text.trim();

  // Il caso dimostrativo vale solo finché il testo è quello: appena viene
  // modificato la run non può più riprodurre artefatti registrati per un testo
  // diverso, e diventa LIVE.
  const matchingDemo = useMemo(
    () => cases.find((demo) => demo.clinical_text.trim() === trimmed) ?? null,
    [cases, trimmed],
  );

  const mode = matchingDemo ? 'FROZEN_REPLAY' : 'LIVE';
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

        {trimmed.length > 0 && (
          <Tooltip
            title={
              mode === 'FROZEN_REPLAY'
                ? 'Testo identico a un caso dimostrativo: gli stage documentali riprodurranno gli artefatti congelati del pilot, che sono risposte reali del modello registrate.'
                : 'Testo inedito: il parser verrà chiamato davvero. Gli stage documentali dipendono dalla cache dei documenti, oggi assente, e produrranno zero paper selezionati.'
            }
          >
            <Chip
              label={mode === 'FROZEN_REPLAY' ? 'replay artefatti congelati' : 'run live'}
              size="small"
              sx={{
                height: 22, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
                backgroundColor: color.stone, color: color.slate, borderRadius: '6px',
              }}
            />
          </Tooltip>
        )}
      </Stack>

      {mode === 'LIVE' && trimmed.length > 0 && (
        <Alert severity="info" sx={{ mt: 2, borderRadius: '8px', fontSize: 13 }}>
          Testo inedito: nessun artefatto congelato esiste per questo caso. Il parser
          verrà chiamato realmente; gli stage 6-10 dipendono dalla cache documentale,
          oggi assente, quindi non produrranno citazioni. Per vedere una QUOTE
          accettata end-to-end, usa un caso dimostrativo.
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
