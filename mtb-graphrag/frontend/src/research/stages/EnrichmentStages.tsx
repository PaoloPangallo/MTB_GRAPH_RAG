/**
 * Stage 9 e 10: ciò che il modello propone, e ciò che il codice ne accetta.
 *
 * Sono due stage e non uno perché la proposta e la sua ammissione hanno autori
 * diversi. Il Paper Context Enricher propone una citazione oppure si astiene;
 * il validatore controlla deterministicamente la citazione nella Source Unit;
 * per EVIDENCE_DRUG un confronto semantico LLM precede l'ammissione deterministica.
 * Una quote rigettata resta visibile qui — serve
 * all'audit — ma non entra nel dossier, e la vista deve rendere impossibile
 * confondere le due cose.
 *
 * Il modello non decide mai status, direzione, gate o bucket.
 */

import { Box, Stack, Typography } from '@mui/material';
import StructuredValue from '../values/StructuredValue';
import { color, font, reasonLabel } from '../tokens';
import { Badge, Card, Empty, Field, Mono, Note, ReasonCodeList, ReplayBadge, SectionLabel } from './kit';
import { num, rows, text } from './preview';

interface StageProps {
  preview: Record<string, unknown>;
}

/** Esiti di validazione, con il tono che ne riflette la conseguenza. */
const OUTCOME_TONE: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = {
  ENRICHMENT_ACCEPTED: 'good',
  ENRICHMENT_V2_ACCEPTED: 'good',
  ENRICHMENT_ACCEPTED_WITH_WARNING: 'warn',
  ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY: 'warn',
  ENRICHMENT_ABSTAINED: 'neutral',
  ENRICHMENT_V2_ABSTAINED: 'neutral',
  ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS: 'warn',
  REJECTED_SOURCE_UNIT: 'bad',
  REJECTED_QUOTE_NOT_FOUND: 'bad',
  REJECTED_CONTEXT_MISMATCH: 'bad',
  REJECTED_SUMMARY_UNGROUNDED: 'bad',
  REJECTED_CLINICAL_RECOMMENDATION: 'bad',
};

export function EnricherStage({ preview }: StageProps) {
  const calls = rows(preview, 'calls');

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5, flexWrap: 'wrap' }}>
        <Badge label="LLM" tone="llm" />
        <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
          Il modello propone una citazione o si astiene. Non assegna status, direzione, gate o bucket.
        </Typography>
      </Stack>

      <SectionLabel>Chiamate all’enricher ({calls.length})</SectionLabel>
      {calls.length === 0 && (
        <Empty>
          Nessuna chiamata: nessun paper è stato selezionato, quindi non c’era
          nulla da leggere.
        </Empty>
      )}

      {calls.map((call, index) => {
        const enrichment = call.enrichment as Record<string, unknown> | null;
        const quote = text(enrichment?.quote) ?? text(enrichment?.author_claim_quote);
        const decision = text(enrichment?.decision) ?? (quote ? 'QUOTE' : enrichment ? 'ABSTAIN' : 'NON DISPONIBILE');

        return (
          <Card key={index}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1.5 }}>
              <Badge
                label={decision}
                tone={decision === 'QUOTE' ? 'good' : 'neutral'}
                title={decision === 'QUOTE'
                  ? 'Il modello ha proposto una frase letterale. La sua ammissione è decisa dallo stage successivo.'
                  : 'Il modello non ha trovato una osservazione letterale applicabile e si è astenuto. È un esito normale.'}
              />
              <Mono>{text(call.paper_id) ?? '—'}</Mono>
              {call.replayed === true && <ReplayBadge />}
            </Stack>

            {quote && (
              <Box sx={{ mb: 1.5 }}>
                <SectionLabel>Citazione proposta</SectionLabel>
                <Typography sx={{
                  fontFamily: font.body, fontSize: 14, lineHeight: 1.6, color: color.ink,
                  backgroundColor: color.stone, p: 1.5, borderRadius: '6px', fontStyle: 'italic', overflowWrap: 'anywhere',
                }}>
                  “{quote}”
                </Typography>
              </Box>
            )}

            <Field label="Candidate"><Mono>{text(call.candidate_id) ?? '—'}</Mono></Field>
            {enrichment?.observed_relation != null && <Field label="Relazione osservata"><StructuredValue value={enrichment.observed_relation} /></Field>}
            {enrichment?.observed_evidence_type != null && <Field label="Tipo di evidenza osservata"><StructuredValue value={enrichment.observed_evidence_type} /></Field>}
            <Field label="Source unit proposta">
              <StructuredValue value={enrichment?.source_unit_id} />
            </Field>
            <Field label="Author context summary">
              <StructuredValue value={enrichment?.author_context_summary} />
            </Field>
            {!quote && (
              <Field label="Motivo dell’astensione">
                <StructuredValue value={enrichment?.abstain_reason ?? enrichment?.abstention_reason} />
              </Field>
            )}
            <Field label="Modello"><Mono>{text(call.model) ?? '—'}</Mono></Field>
            <Field label="Prompt version"><Mono>{text(call.prompt_version) ?? '—'}</Mono></Field>
            <Field label="Transport version"><Mono>{text(call.transport_version) ?? '—'}</Mono></Field>
            <Field label="Transport result">
              {text(call.transport_result)
                ? <Badge label={text(call.transport_result)!} />
                : <Empty>non disponibile</Empty>}
            </Field>
            <Field label="Token">
              <Mono>
                {num(call.input_tokens) ?? '—'} in · {num(call.output_tokens) ?? '—'} out
              </Mono>
            </Field>
            <Field label="Latenza">
              <Mono>{num(call.latency_ms) !== null ? `${Math.round(num(call.latency_ms)!)} ms` : '—'}</Mono>
            </Field>
          </Card>
        );
      })}
    </Box>
  );
}

export function ValidationStage({ preview }: StageProps) {
  const validations = rows(preview, 'validations');
  const accepted = preview.accepted_outcomes;
  const semantic = preview.semantic_verification as Record<string, unknown> | undefined;
  const semanticCalls = num(semantic?.attempted_calls) ?? 0;

  return (
    <Box>
      <SectionLabel>Verifica della citazione e della relazione</SectionLabel>
      <Note>
        Una citazione letterale valida non dimostra da sola la relazione. La verifica
        distingue provenienza, controlli strutturali, allineamento semantico e ammissione finale.
        Per EVIDENCE_DRUG il confronto semantico usa un modello indipendente quando
        i controlli strutturali passano; la regola di ammissione finale è deterministica.
      </Note>
      {semanticCalls > 0 && <Box sx={{ my: 1.5 }}>
        <Badge label={`Confronto semantico LLM: ${semanticCalls} ${semanticCalls === 1 ? 'chiamata' : 'chiamate'}`} tone="llm" />
        <Note>Le interpretazioni del modello restano fallibili. La regola deterministica richiede risultato osservato, scope compatibile, inferenza diretta e certezza della relazione.</Note>
        <Field label="Provenienza del confronto semantico"><StructuredValue value={semantic} /></Field>
      </Box>}
      <Field label="Esiti ammessi"><StructuredValue value={accepted} /></Field>

      <Box sx={{ mt: 2.5 }}>
        <SectionLabel>Esiti ({validations.length})</SectionLabel>
        {validations.length === 0 && <Empty>Nessuna validazione: nessuna citazione proposta</Empty>}

        {validations.map((validation, index) => {
          const outcome = text(validation.outcome) ?? 'UNKNOWN';
          const acceptedOutcomes = Array.isArray(accepted) ? accepted : [];
          const quoteValid = validation.quote_valid === true ||
            (validation.quote_valid !== false && acceptedOutcomes.includes(outcome));
          const blockerValue = (validation.document_verification as Record<string, unknown> | null)?.admission_reason_codes;
          const blockers = Array.isArray(blockerValue) ? blockerValue.filter((code): code is string => typeof code === 'string') : [];

          return (
            <Card key={index}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1 }}>
                <Badge label={outcome} tone={OUTCOME_TONE[outcome] ?? 'neutral'} />
                <Badge
                  label={quoteValid ? 'Citazione valida' : 'Citazione non validata'}
                  tone={quoteValid ? 'good' : 'neutral'}
                />
                {validation.replayed === true && <ReplayBadge />}
              </Stack>
              <Field label="Candidate"><Mono>{text(validation.candidate_id) ?? '—'}</Mono></Field>
              <Field label="Paper"><Mono>{text(validation.paper_id) ?? '—'}</Mono></Field>
              {validation.candidate_support != null && <Field label="Confronto con il target (contratto registrato)"><StructuredValue value={validation.candidate_support} /></Field>}
              {validation.document_verification != null && <Field label="Verifica documentale"><StructuredValue value={validation.document_verification} /></Field>}
              {validation.document_verification != null && <ReasonCodeList codes={(validation.document_verification as Record<string, unknown>).admission_reason_codes} />}
              {blockers.map((code, codeIndex) => <Typography key={`${code}-${codeIndex}`} sx={{ fontSize: 13, color: color.slate, my: 0.5 }}>{reasonLabel(code)}</Typography>)}
              <Field label="Reason code">
                <ReasonCodeList codes={validation.reason_codes} />
              </Field>
            </Card>
          );
        })}
      </Box>
    </Box>
  );
}
