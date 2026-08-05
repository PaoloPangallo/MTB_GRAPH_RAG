/**
 * Stage 11 e 12: i controlli deterministici e la classificazione che ne segue.
 *
 * La tabella dei controlli esiste per una distinzione che una support mask nuda
 * non può esprimere. `disease: SUPPORTED` e `direction: SUPPORTED` hanno lo
 * stesso aspetto e non lo stesso significato: il primo è ereditato dal match
 * strutturale dello stage 5, dove la candidate è stata ammessa proprio perché
 * quel match passava; il secondo è deciso qui, sulle citazioni validate. Senza
 * la colonna dell'origine si leggono come quattro conferme indipendenti.
 *
 * I controlli previsti dal design e non implementati restano in tabella. La loro
 * assenza è un fatto sul sistema, e ometterli farebbe sembrare completa una
 * copertura che non lo è.
 */

import { Box, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography } from '@mui/material';
import StructuredValue from '../values/StructuredValue';
import { color, font } from '../tokens';
import { Badge, Card, Empty, Field, Mono, Note, SectionLabel, rows, text } from './kit';

interface StageProps {
  preview: Record<string, unknown>;
}

const SOURCE_TONE: Record<string, 'good' | 'warn' | 'neutral'> = {
  COMPUTED_HERE: 'good',
  INHERITED_VERIFIED_RESULT: 'neutral',
  NOT_IMPLEMENTED: 'warn',
  NOT_APPLICABLE: 'neutral',
};

const SOURCE_HELP: Record<string, string> = {
  COMPUTED_HERE: 'Controllo realmente calcolato in questo stage.',
  INHERITED_VERIFIED_RESULT:
    'Risultato già verificato in uno stage precedente e riutilizzato qui: non è una seconda conferma.',
  NOT_IMPLEMENTED:
    'Controllo previsto dal design ma non disponibile in questa implementazione.',
  NOT_APPLICABLE:
    'Controllo non applicabile a questo caso: non è un controllo fallito.',
};

function CheckTable({ checks }: { checks: Array<Record<string, unknown>> }) {
  if (checks.length === 0) return <Empty>Nessun controllo dichiarato</Empty>;

  return (
    <Box sx={{ overflowX: 'auto', border: `1px solid ${color.hairline}`, borderRadius: '6px' }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            {['Controllo', 'Origine', 'Esito', 'Stage di origine', 'Reason code', 'Versione'].map((head) => (
              <TableCell key={head} sx={{
                fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
                textTransform: 'uppercase', color: color.muted, whiteSpace: 'nowrap',
              }}>
                {head}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {checks.map((check, index) => {
            const source = text(check.source) ?? 'UNKNOWN';
            return (
              <TableRow key={index}>
                <TableCell sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>
                  {text(check.label) ?? text(check.check_id) ?? '—'}
                </TableCell>
                <TableCell>
                  <Tooltip title={SOURCE_HELP[source] ?? ''}>
                    <Box component="span">
                      <Badge label={source} tone={SOURCE_TONE[source] ?? 'neutral'} />
                    </Box>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <StructuredValue value={check.result} />
                </TableCell>
                <TableCell sx={{ fontFamily: font.mono, fontSize: 11, color: color.slate }}>
                  {text(check.source_stage) ?? '—'}
                </TableCell>
                <TableCell sx={{ fontFamily: font.mono, fontSize: 11, color: color.slate }}>
                  {text(check.reason_code) ?? '—'}
                </TableCell>
                <TableCell sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
                  {text(check.version) ?? '—'}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}

export function DeterministicChecksStage({ preview }: StageProps) {
  const byCandidate = rows(preview, 'checks_by_candidate');

  return (
    <Box>
      <SectionLabel>Controlli deterministici</SectionLabel>
      <Note>
        Ogni controllo dichiara dove è stato deciso. Un esito ereditato non è una
        conferma aggiuntiva, e un controllo non implementato non è un controllo
        passato.
      </Note>

      {byCandidate.length === 0 && <Empty>Nessun controllo: nessuna candidate valutata</Empty>}

      {byCandidate.map((entry, index) => {
        const checks = Array.isArray(entry.checks)
          ? entry.checks.filter((c): c is Record<string, unknown> => typeof c === 'object' && c !== null)
          : [];

        return (
          <Box key={index} sx={{ mb: 3 }}>
            <Mono>{text(entry.candidate_id) ?? `candidate ${index + 1}`}</Mono>
            <Box sx={{ mt: 1 }}>
              <CheckTable checks={checks} />
            </Box>
            {Array.isArray(entry.direction_consistencies) && entry.direction_consistencies.length > 0 && (
              <Box sx={{ mt: 1.5 }}>
                <Field label="Coerenza di direzione">
                  <StructuredValue value={entry.direction_consistencies} />
                </Field>
              </Box>
            )}
          </Box>
        );
      })}
    </Box>
  );
}

export function StatusStage({ preview }: StageProps) {
  const statuses = rows(preview, 'statuses');

  return (
    <Box>
      <SectionLabel>Classificazione deterministica</SectionLabel>
      <Note>
        Status e bucket sono calcolati da codice. Nessun modello contribuisce a
        questo risultato, e nessuno di questi valori è una raccomandazione clinica.
      </Note>

      {statuses.length === 0 && <Empty>Nessuno status assegnato</Empty>}

      {statuses.map((entry, index) => (
        <Card key={index}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1 }}>
            <Mono>{text(entry.candidate_id) ?? `candidate ${index + 1}`}</Mono>
            {text(entry.status) && <Badge label={text(entry.status)!} />}
            {text(entry.gate_bucket) && <Badge label={text(entry.gate_bucket)!} />}
          </Stack>
          <Field label="Avvisi"><StructuredValue value={entry.warnings} /></Field>
        </Card>
      ))}

      <Typography sx={{
        mt: 2, fontFamily: font.body, fontSize: 12, color: color.slate,
      }}>
        `PRIMARY_BUCKET` è una classificazione interna di evidenza, non una
        raccomandazione terapeutica.
      </Typography>
    </Box>
  );
}
