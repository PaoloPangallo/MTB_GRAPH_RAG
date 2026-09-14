import { Accordion, AccordionDetails, AccordionSummary, Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { color, font, radius, reasonLabel } from './tokens';

/**
 * Vista narrativa verificata.
 *
 * Il frontend non decide **nulla**: legge `presentation_mode`, deciso dal
 * Narrative Verifier deterministico nel backend. Se la narrativa non e' stata
 * verificata non viene mostrata, e al suo posto compare il motivo.
 *
 * E' la stessa regola che ha chiuso ISS-003 per le quote: la fonte
 * dell'accettazione sta nel backend, mai in un'inferenza del client.
 */

export type PresentationMode = 'VERIFIED_NARRATIVE' | 'STRUCTURED_DOSSIER_FALLBACK';

export interface CandidateNarrative {
  candidate_id: string;
  text: string;
}

export interface Narrative {
  narrative_summary?: string | null;
  candidate_narratives?: CandidateNarrative[] | null;
  limitations_summary?: string | null;
  closing_note?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  narrative_hash?: string | null;
}

export interface NarrativeVerification {
  status?: string | null;
  reason_codes?: string[] | null;
  verifier_version?: string | null;
  narrative_hash?: string | null;
  input_hash?: string | null;
}

export interface PresentationSource {
  paper_id: string;
  source_unit_id?: string | null;
  quote_available: boolean;
  validated_quote?: string | null;
  source_unit_text?: string | null;
}

export interface CandidatePresentation {
  candidate_id: string;
  intervention?: string | null;
  graph_relation: string;
  canonical_status: string;
  support_direction: string;
  documentary_support_state: string;
  sources: PresentationSource[];
  critical_notices: string[];
  generated_explanation?: string | null;
}

const DOCUMENTARY_STATE_LABELS: Record<string, string> = {
  DOCUMENTARY_EVIDENCE_AVAILABLE: 'Documentazione validata disponibile',
  NO_VALIDATED_DOCUMENTARY_EVIDENCE: 'Nessun supporto documentale validato',
  SOURCE_DOES_NOT_SUPPORT: 'La fonte non supporta la relazione',
  CONTRADICTORY_DOCUMENTARY_EVIDENCE: 'Evidenza documentale contraddittoria',
  AMBIGUOUS_DOCUMENTARY_STATE: 'Stato documentale non conclusivo',
};

function documentaryStateLabel(state: string): string {
  return DOCUMENTARY_STATE_LABELS[state] ?? state;
}

export interface NarrativePresentation {
  contract_version: string;
  presentation_mode: PresentationMode | string;
  summary?: string | null;
  candidates: CandidatePresentation[];
  canonical_limitations: string[];
  limitations_explanation?: string | null;
  closing_note?: string | null;
  verification?: NarrativeVerification | null;
}

interface Props {
  narrative: Narrative | null;
  presentation?: NarrativePresentation | null;
  presentationMode: PresentationMode | string;
  verification: NarrativeVerification | null;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{
      fontFamily: font.mono, fontSize: 11, letterSpacing: '0.08em',
      color: color.muted, textTransform: 'uppercase', mb: 1,
    }}>
      {children}
    </Typography>
  );
}

export default function NarrativeView({ narrative, presentation, presentationMode, verification }: Props) {
  const verified = presentationMode === 'VERIFIED_NARRATIVE' && narrative != null;

  return (
    <Box sx={{
      border: `1px solid ${color.borderLight}`, borderRadius: `${radius.md}px`, p: 2.5, mb: 2,
    }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5 }}>
        <Typography sx={{
          fontFamily: font.display, fontSize: 20, letterSpacing: '-0.01em', color: color.ink,
        }}>
          Narrativa
        </Typography>
        <Tooltip title="Lo stato e' deciso dal Narrative Verifier deterministico nel backend.">
          <Chip
            label={verified ? 'VERIFICATA' : 'NON DISPONIBILE — FALLBACK STRUTTURATO'}
            size="small"
            sx={{
              height: 20, fontFamily: font.mono, fontSize: 10, borderRadius: '4px',
              backgroundColor: verified ? color.stone : color.canvas,
              color: verified ? color.body : color.muted,
            }}
          />
        </Tooltip>
      </Stack>

      <Typography sx={{ fontFamily: font.body, fontSize: 11, color: color.slate, mb: 2 }}>
        Riformulazione leggibile di un dossier gia' deciso. Non modifica status, gate,
        support mask o provenance: il dossier strutturato resta la fonte canonica.
      </Typography>

      {verified ? (
        <>
          {(presentation?.summary ?? narrative.narrative_summary) && (
            <Box sx={{ mb: 2 }}>
              <SectionTitle>Sintesi</SectionTitle>
              <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.ink }}>
                {presentation?.summary ?? narrative.narrative_summary}
              </Typography>
            </Box>
          )}

          {presentation ? presentation.candidates.map((entry) => (
            <Box key={entry.candidate_id} sx={{ mb: 2, pb: 2, borderBottom: `1px solid ${color.borderLight}` }}>
              <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 0.75 }}>
                <Typography sx={{ fontFamily: font.display, fontSize: 16, color: color.ink }}>
                  {entry.intervention || entry.candidate_id}
                </Typography>
                <Chip label={entry.canonical_status} size="small" />
                <Chip label={entry.support_direction} size="small" variant="outlined" />
                <Chip label={documentaryStateLabel(entry.documentary_support_state)} size="small" variant="outlined" />
              </Stack>
              <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, mb: 0.5 }}>
                {entry.candidate_id} · {entry.graph_relation}
              </Typography>
              {entry.critical_notices.length > 0 && (
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', mb: 1 }} role="alert">
                  {entry.critical_notices.map((notice) => (
                    <Chip key={notice} label={reasonLabel(notice)} size="small"
                          sx={{ backgroundColor: color.canvas, color: color.body }} />
                  ))}
                </Stack>
              )}
              {entry.generated_explanation && (
                <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body, mb: 1 }}>
                  {entry.generated_explanation}
                </Typography>
              )}
              {entry.sources.map((source) => (
                <Accordion key={`${source.paper_id}-${source.source_unit_id ?? ''}`} disableGutters elevation={0}
                           sx={{ backgroundColor: color.canvas }}>
                  <AccordionSummary>
                    <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.body }}>
                      Fonte selezionata: {source.paper_id}{source.source_unit_id ? ` · ${source.source_unit_id}` : ''}
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                      <>
                        <Box component="span" sx={{ display: 'block', mb: 0.5 }}>
                          Testo della SourceUnit:
                        </Box>
                        <Box component="span" sx={{ display: 'block', mb: 1 }}>
                          {source.source_unit_text || 'Testo della SourceUnit non disponibile.'}
                        </Box>
                        <Box component="span" sx={{ display: 'block', mb: 0.5 }}>
                          Quote validata: {source.quote_available ? 'sì' : 'no'}
                        </Box>
                        {source.quote_available && source.validated_quote
                          ? source.validated_quote : 'Nessuna citazione validata disponibile.'}
                      </>
                    </Typography>
                  </AccordionDetails>
                </Accordion>
              ))}
            </Box>
          )) : (narrative.candidate_narratives ?? []).map((entry) => (
            <Box key={entry.candidate_id} sx={{ mb: 1.5 }}>
              <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>{entry.candidate_id}</Typography>
              <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>{entry.text}</Typography>
            </Box>
          ))}

          {(presentation?.canonical_limitations?.length || presentation?.limitations_explanation || narrative.limitations_summary) && (
            <Box sx={{ mt: 2 }}>
              <SectionTitle>Limitazioni</SectionTitle>
              <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                {presentation?.limitations_explanation ?? narrative.limitations_summary}
              </Typography>
              {(presentation?.canonical_limitations ?? []).map((limitation) => (
                <Chip key={limitation} label={reasonLabel(limitation)} size="small" sx={{ mt: 0.75, mr: 0.5 }} />
              ))}
            </Box>
          )}

          {(presentation?.closing_note ?? narrative.closing_note) && (
            <Typography sx={{
              fontFamily: font.body, fontSize: 12, color: color.slate, mt: 1.5, fontStyle: 'italic',
            }}>
              {presentation?.closing_note ?? narrative.closing_note}
            </Typography>
          )}
        </>
      ) : (
        <Box>
          <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body, mb: 1 }}>
            La narrativa non ha superato la verifica deterministica e non viene mostrata.
            Il dossier strutturato qui sopra resta completo e consultabile.
          </Typography>
          {(verification?.reason_codes ?? []).length > 0 && (
            <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap', mt: 1 }}>
              {(verification?.reason_codes ?? []).map((code) => (
                <Chip
                  key={code}
                  label={reasonLabel(code)}
                  size="small"
                  sx={{
                    height: 20, fontFamily: font.mono, fontSize: 10, borderRadius: '4px',
                    backgroundColor: color.canvas, color: color.body,
                  }}
                />
              ))}
            </Stack>
          )}
        </Box>
      )}

      {verification?.verifier_version && (
        <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, mt: 2 }}>
          {verification.verifier_version}
          {verification.narrative_hash ? ` · ${verification.narrative_hash.slice(0, 12)}` : ''}
        </Typography>
      )}
    </Box>
  );
}
