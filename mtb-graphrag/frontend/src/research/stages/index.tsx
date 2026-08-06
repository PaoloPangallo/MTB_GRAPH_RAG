/**
 * Instrada uno stage alla vista che sa leggerlo.
 *
 * Il fallback è deliberatamente `StructuredValue` e non un blocco JSON: uno
 * stage privo di vista dedicata resta comunque leggibile, e nessun ramo può
 * produrre `[object Object]`. Uno stage saltato non mostra un output vuoto ma
 * il motivo per cui non è stato eseguito, perché un preview vuoto e uno stage
 * non eseguito hanno lo stesso aspetto e conseguenze diverse.
 */

import { Box, Typography } from '@mui/material';
import StructuredValue from '../values/StructuredValue';
import { color, font, reasonLabel } from '../tokens';
import type { PipelineStage } from '../types';
import { MatchVerifierStage, ParserStage } from './CaseContextStages';
import EligibilityStage from './EligibilityStage';
import { DeterministicChecksStage, StatusStage } from './DeterministicStages';
import { EnricherStage, ValidationStage } from './EnrichmentStages';
import {
  DocumentResolutionStage, GraphCandidateStage, PaperSelectionStage, SourceUnitStage,
} from './RetrievalStages';
import { Badge, Note, SectionLabel } from './kit';

interface StageOutputProps {
  stage: PipelineStage;
  clinicalText?: string;
}

function NotExecuted({ stage }: { stage: PipelineStage }) {
  const code = stage.reason_codes[0] ?? 'NOT_EXECUTED';
  const notImplemented = code === 'NOT_IMPLEMENTED';

  return (
    <Box>
      <Badge label={notImplemented ? 'NOT_IMPLEMENTED' : 'NOT_EXECUTED'} tone="warn" />
      <Typography sx={{ mt: 1.5, fontFamily: font.body, fontSize: 14, color: color.body }}>
        {notImplemented
          ? 'Stage previsto dal contratto e privo di implementazione. Non è stato eseguito, e dichiararlo eseguito sarebbe simulazione.'
          : `Stage non eseguito: ${reasonLabel(code)}.`}
      </Typography>
      {stage.reason_codes.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <SectionLabel>Reason code</SectionLabel>
          <StructuredValue value={stage.reason_codes} />
        </Box>
      )}
    </Box>
  );
}

export default function StageOutput({ stage, clinicalText }: StageOutputProps) {
  if (stage.status === 'SKIPPED') return <NotExecuted stage={stage} />;

  const preview = stage.output_preview ?? {};

  switch (stage.stage_id) {
    case 'stage_1_case_input':
      return (
        <Box>
          <SectionLabel>Ingresso</SectionLabel>
          <Note>Testo clinico in linguaggio libero, non campi strutturati.</Note>
          {clinicalText && (
            <Box sx={{
              fontFamily: font.body, fontSize: 14, lineHeight: 1.6, color: color.body,
              backgroundColor: color.stone, p: 2, borderRadius: '8px', mb: 2,
            }}>
              {clinicalText}
            </Box>
          )}
          <StructuredValue value={preview} />
        </Box>
      );

    case 'stage_2_casecontext_parser':
      return <ParserStage preview={preview} producer={stage.producer} />;

    case 'stage_3_casecontext_match':
      return <MatchVerifierStage preview={preview} producer={stage.producer} clinicalText={clinicalText} />;

    case 'stage_3b_pre_retrieval_eligibility_gate':
      return <EligibilityStage preview={preview} />;

    case 'stage_5_kg_retrieval':
      return <GraphCandidateStage preview={preview} />;

    case 'stage_6_document_resolution':
      return <DocumentResolutionStage preview={preview} />;

    case 'stage_7_source_units':
      return <SourceUnitStage preview={preview} />;

    case 'stage_8_paper_selection':
      return <PaperSelectionStage preview={preview} />;

    case 'stage_9_paper_context_enricher':
      return <EnricherStage preview={preview} />;

    case 'stage_10_enrichment_validation':
      return <ValidationStage preview={preview} />;

    case 'stage_11_deterministic_gates':
      return <DeterministicChecksStage preview={preview} />;

    case 'stage_12_status':
      return <StatusStage preview={preview} />;

    default:
      return <StructuredValue value={preview} />;
  }
}
