/**
 * Vista del Pre-Retrieval Eligibility Gate.
 *
 * Il gate è lo stage in cui un input vuoto, fuori dominio, non azionabile o
 * contraddittorio si ferma. La vista mostra **la decisione presa dal backend**,
 * mai una ricalcolata qui: lo stato, i motivi e gli stage saltati arrivano già
 * risolti nel preview. Ricostruirli nel browser significherebbe avere due
 * autorità sulla stessa decisione.
 */

import { Box, Stack, Typography } from '@mui/material';
import StructuredValue from '../values/StructuredValue';
import { color, font, reasonLabel } from '../tokens';
import { Badge, Empty, Field, Note, SectionLabel } from './kit';

type Tone = 'good' | 'warn' | 'bad' | 'neutral';

/** Tono del badge per ogni stato. Lo **stato** resta quello del backend. */
const TONE_BY_STATUS: Record<string, Tone> = {
  ELIGIBLE_FOR_RETRIEVAL: 'good',
  INVALID_INPUT: 'bad',
  OUT_OF_SCOPE: 'warn',
  NON_ACTIONABLE_MEDICAL_INPUT: 'warn',
  INSUFFICIENT_ONCOLOGY_CONTEXT: 'warn',
  MISSING_REQUIRED_FIELDS: 'warn',
  CONTRADICTORY_CASE_CONTEXT: 'bad',
  ADVERSARIAL_OR_CONTROL_INPUT: 'bad',
  AMBIGUOUS_CASE_CONTEXT: 'warn',
};

const LABEL_BY_STATUS: Record<string, string> = {
  ELIGIBLE_FOR_RETRIEVAL: 'ELIGIBLE',
  INVALID_INPUT: 'INVALID INPUT',
  OUT_OF_SCOPE: 'OUT OF SCOPE',
  NON_ACTIONABLE_MEDICAL_INPUT: 'NON ACTIONABLE',
  INSUFFICIENT_ONCOLOGY_CONTEXT: 'INSUFFICIENT CONTEXT',
  MISSING_REQUIRED_FIELDS: 'MISSING FIELDS',
  CONTRADICTORY_CASE_CONTEXT: 'CONTRADICTORY',
  ADVERSARIAL_OR_CONTROL_INPUT: 'CONTROL INPUT',
  AMBIGUOUS_CASE_CONTEXT: 'AMBIGUOUS',
};

interface Mention {
  raw_text?: string;
  entity_type?: string;
  semantic_role?: string;
  assertion_status?: string;
  rejection_reason?: string | null;
}

interface Contradiction {
  contradiction_id?: string;
  type?: string;
  normalized_entity?: string;
  reason_code?: string;
  severity?: string;
}

interface ControlSpan {
  quote?: string;
  reason_code?: string;
}

interface EligibilityPreview {
  eligibility_status?: string;
  eligible?: boolean;
  reason_codes?: string[];
  verified_fields?: Record<string, unknown>;
  missing_required_fields?: string[];
  rejected_mentions?: Mention[];
  symptom_mentions?: Mention[];
  control_instruction_spans?: ControlSpan[];
  contradictions?: Contradiction[];
  scope_evidence?: string[];
  forbidden_downstream_stages?: string[];
  policy_version?: string;
  producer?: string;
}

function MentionRow({ mention }: { mention: Mention }) {
  return (
    <Box sx={{ py: 0.5, borderBottom: `1px solid ${color.hairline}` }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography sx={{ fontFamily: font.mono, fontSize: 13, color: color.body }}>
          {mention.raw_text ?? '—'}
        </Typography>
        {mention.entity_type && <Badge label={mention.entity_type} tone="neutral" />}
        {mention.assertion_status && mention.assertion_status !== 'ASSERTED' && (
          <Badge label={mention.assertion_status} tone="warn" />
        )}
        {mention.rejection_reason && (
          <Badge label={reasonLabel(mention.rejection_reason)} tone="bad" />
        )}
      </Stack>
    </Box>
  );
}

export default function EligibilityStage({ preview }: { preview: EligibilityPreview }) {
  const status = preview.eligibility_status ?? 'UNKNOWN';
  const rejected = preview.rejected_mentions ?? [];
  const symptoms = preview.symptom_mentions ?? [];
  const controlSpans = preview.control_instruction_spans ?? [];
  const contradictions = preview.contradictions ?? [];
  const missing = preview.missing_required_fields ?? [];
  const skipped = preview.forbidden_downstream_stages ?? [];

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1.5 }}>
        <Badge
          label={LABEL_BY_STATUS[status] ?? status}
          tone={TONE_BY_STATUS[status] ?? 'neutral'}
        />
        <Badge label={preview.producer ?? 'DETERMINISTIC'} tone="neutral" />
      </Stack>

      <Note>
        Decisione deterministica presa prima del retrieval. Nessun modello è coinvolto:
        lo stato, i motivi e gli stage saltati arrivano già risolti dal backend.
      </Note>

      {(preview.reason_codes ?? []).length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Motivo</SectionLabel>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            {(preview.reason_codes ?? []).map((code) => (
              <Badge key={code} label={reasonLabel(code)} tone="neutral" />
            ))}
          </Stack>
        </Box>
      )}

      <Box sx={{ mt: 2 }}>
        <SectionLabel>Campi verificati</SectionLabel>
        {preview.verified_fields
          ? <StructuredValue value={preview.verified_fields} />
          : <Empty>Nessun campo verificato.</Empty>}
      </Box>

      {(preview.scope_evidence ?? []).length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Ancoraggi di scope</SectionLabel>
          <StructuredValue value={preview.scope_evidence} />
        </Box>
      )}

      {missing.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Campi mancanti</SectionLabel>
          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
            {missing.map((field) => <Badge key={field} label={field} tone="warn" />)}
          </Stack>
        </Box>
      )}

      {symptoms.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Sintomi riconosciuti</SectionLabel>
          <Note>Un sintomo non è una diagnosi: non popola lo slot disease.</Note>
          {symptoms.map((mention, index) => (
            <MentionRow key={`symptom-${index}`} mention={mention} />
          ))}
        </Box>
      )}

      {rejected.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Menzioni rifiutate</SectionLabel>
          <Note>
            Riconosciute nel testo ma non accettate come campo clinico. Restano visibili
            per audit.
          </Note>
          {rejected.map((mention, index) => (
            <MentionRow key={`rejected-${index}`} mention={mention} />
          ))}
        </Box>
      )}

      {controlSpans.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Istruzioni rivolte al sistema</SectionLabel>
          <Note>Trattate come contenuto dell&apos;input, non eseguite.</Note>
          {controlSpans.map((span, index) => (
            <Box key={`control-${index}`} sx={{ py: 0.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Badge label={span.reason_code ?? 'CONTROL_INSTRUCTION'} tone="bad" />
                <Typography sx={{ fontFamily: font.mono, fontSize: 12, color: color.slate }}>
                  {span.quote ?? ''}
                </Typography>
              </Stack>
            </Box>
          ))}
        </Box>
      )}

      {contradictions.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Contraddizioni</SectionLabel>
          {contradictions.map((item, index) => (
            <Box key={item.contradiction_id ?? `ctr-${index}`} sx={{ py: 0.5 }}>
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                <Badge
                  label={item.severity === 'BLOCKING' ? 'BLOCKING' : 'WARNING'}
                  tone={item.severity === 'BLOCKING' ? 'bad' : 'warn'}
                />
                <Typography sx={{ fontFamily: font.mono, fontSize: 13, color: color.body }}>
                  {item.normalized_entity ?? item.type ?? ''}
                </Typography>
                {item.reason_code && (
                  <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                    {reasonLabel(item.reason_code)}
                  </Typography>
                )}
              </Stack>
            </Box>
          ))}
        </Box>
      )}

      {skipped.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Stage downstream saltati</SectionLabel>
          <Note>Il caso non è eleggibile: questi stage non vengono eseguiti.</Note>
          <StructuredValue value={skipped} />
        </Box>
      )}

      {preview.policy_version && (
        <Box sx={{ mt: 2 }}>
          <Field label="policy_version">{preview.policy_version}</Field>
        </Box>
      )}
    </Box>
  );
}
