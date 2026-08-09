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
  /** Dal backend: senza cache documentale la pipeline si arresta allo stage 6. */
  documentCacheAvailable?: boolean;
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
  cases, busy, onRun, documentCacheAvailable = true,
}: CaseInputPanelProps) {
  const [text, setText] = useState('');
  const [touchedCaseId, setTouchedCaseId] = useState<string | null>(null);

  const trimmed = text.trim();

  // Un caso dimostrativo compila il testo; se il testo resta quello, la run
  // parte dal caso e non da un identificativo inventato. È una comodità di
  // identificazione, non un percorso di esecuzione diverso.
  const matchingDemo = useMemo(
    () => cases.find((demo) => demo.clinical_text.trim() === trimmed) ?? null,
    [cases, trimmed],
  );

  const canRun = trimmed.length > 0 && !busy && documentCacheAvailable;

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
          data-testid="run-pipeline"
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
          La cache documentale non è disponibile: la pipeline si arresterebbe allo
          stage 6 con <code>DOCUMENT_CACHE_UNAVAILABLE</code>. Nessun artefatto
          registrato viene usato al suo posto — configura
          {' '}<code>RESEARCH_DOCUMENT_CACHE_PATH</code>.
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
