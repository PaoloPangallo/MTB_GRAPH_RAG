/**
 * Stage 2 e 3: estrazione del CaseContext e sua verifica contro il testo.
 *
 * Vanno tenuti separati perché rispondono a due domande diverse. Lo stage 2 dice
 * *cosa il modello ha estratto*; lo stage 3 dice *se quell'estrazione trova
 * riscontro letterale nel testo*. Fonderli in un unico "CaseContext
 * normalizzato" — com'era nella vista precedente — cancella esattamente il
 * controllo che rende il parser verificabile: senza il confronto campo per
 * campo, un'allucinazione del modello e un'estrazione corretta hanno lo stesso
 * aspetto.
 */

import { Box, Stack, Typography } from '@mui/material';
import StructuredValue from '../values/StructuredValue';
import { color, font } from '../tokens';
import { Badge, Card, Empty, Field, Mono, Note, SectionLabel, rows, text } from './kit';

interface StagePreview {
  preview: Record<string, unknown>;
  producer: { model?: string | null; prompt_version?: string | null; component: string; version: string };
  clinicalText?: string;
}

/** Colore dell'esito di verifica di un campo. */
const MATCH_TONE: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = {
  MATCH: 'good',
  UNCERTAIN: 'warn',
  MISMATCH: 'bad',
  MISSING_IN_TEXT: 'bad',
};

export function ParserStage({ preview, producer }: StagePreview) {
  const caseContext = preview.case_context as Record<string, unknown> | undefined;
  const transport = text(preview.transport_result);

  return (
    <Box>
      <SectionLabel>Chiamata al modello</SectionLabel>
      <Field label="Modello"><Mono>{producer.model ?? 'non disponibile'}</Mono></Field>
      <Field label="Prompt version"><Mono>{producer.prompt_version ?? 'non disponibile'}</Mono></Field>
      <Field label="Transport result">
        {transport
          ? <Badge label={transport} tone={transport === 'FORCED_TOOL_VALID' ? 'good' : 'bad'} />
          : <Empty>non disponibile</Empty>}
      </Field>
      <Field label="Query intent">
        <StructuredValue value={preview.query_intent} />
      </Field>

      <Box sx={{ mt: 3 }}>
        <SectionLabel>CaseContext estratto dal modello</SectionLabel>
        <Note>
          Output grezzo del parser, prima di qualunque normalizzazione
          deterministica. La verifica campo per campo è nello stage successivo.
        </Note>
        {caseContext
          ? <StructuredValue value={caseContext} />
          : <Empty>Il parser non ha prodotto un CaseContext</Empty>}
      </Box>
    </Box>
  );
}

export function MatchVerifierStage({ preview, clinicalText }: StagePreview) {
  const records = rows(preview, 'records');
  const pass = preview.essential_fields_pass;

  return (
    <Box>
      <SectionLabel>Esito complessivo</SectionLabel>
      <Field label="Campi essenziali">
        <Badge
          label={pass === true ? 'PASS' : 'FAIL'}
          tone={pass === true ? 'good' : 'bad'}
          title={pass === true
            ? 'Ogni campo essenziale trova riscontro nel testo: la pipeline prosegue.'
            : 'Un campo essenziale non trova riscontro: la pipeline si ferma qui, ed è l’esito corretto.'}
        />
      </Field>
      <Field label="Avvisi"><StructuredValue value={preview.warnings} /></Field>

      {clinicalText && (
        <Box sx={{ mt: 3 }}>
          <SectionLabel>Testo clinico di partenza</SectionLabel>
          <Box sx={{
            fontFamily: font.body, fontSize: 13, lineHeight: 1.6, color: color.body,
            backgroundColor: color.stone, p: 2, borderRadius: '8px',
          }}>
            {clinicalText}
          </Box>
        </Box>
      )}

      <Box sx={{ mt: 3 }}>
        <SectionLabel>Confronto campo per campo</SectionLabel>
        <Note>
          Per ogni campo estratto: il testo che lo sostiene e la sua posizione
          esatta nel testo originale. È il confronto che il relatore può rifare
          a mano.
        </Note>

        {records.length === 0 && <Empty>Nessun campo verificato</Empty>}

        {records.map((record, index) => {
          const status = text(record.status) ?? 'UNKNOWN';
          const supporting = text(record.supporting_text);
          const start = record.start_offset;
          const end = record.end_offset;

          return (
            <Card key={index}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1 }}>
                <Typography sx={{ fontFamily: font.body, fontSize: 14, fontWeight: 600, color: color.ink }}>
                  {text(record.field) ?? `campo ${index + 1}`}
                </Typography>
                <Badge label={status} tone={MATCH_TONE[status] ?? 'neutral'} />
                {text(record.reason_code) && <Badge label={text(record.reason_code)!} />}
              </Stack>

              <Field label="Valore estratto">
                <StructuredValue value={record.casecontext_value} />
              </Field>
              {record.normalized_value !== undefined && (
                <Field label="Normalizzato">
                  <StructuredValue value={record.normalized_value} />
                </Field>
              )}
              <Field label="Testo di supporto">
                {supporting
                  ? (
                    <Typography sx={{
                      fontFamily: font.body, fontSize: 13, color: color.body,
                      borderLeft: `2px solid ${color.hairline}`, pl: 1.5, fontStyle: 'italic',
                    }}>
                      “{supporting}”
                    </Typography>
                  )
                  : <Empty>Nessun testo di supporto trovato</Empty>}
              </Field>
              <Field label="Offset">
                {typeof start === 'number' && typeof end === 'number'
                  ? <Mono>{start}–{end}</Mono>
                  : <Empty>non disponibile</Empty>}
              </Field>
            </Card>
          );
        })}
      </Box>
    </Box>
  );
}
