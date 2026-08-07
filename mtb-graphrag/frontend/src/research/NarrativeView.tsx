import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
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

interface Props {
  narrative: Narrative | null;
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

export default function NarrativeView({ narrative, presentationMode, verification }: Props) {
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
          {narrative.narrative_summary && (
            <Box sx={{ mb: 2 }}>
              <SectionTitle>Sintesi</SectionTitle>
              <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.ink }}>
                {narrative.narrative_summary}
              </Typography>
            </Box>
          )}

          {(narrative.candidate_narratives ?? []).map((entry) => (
            <Box key={entry.candidate_id} sx={{ mb: 1.5 }}>
              <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
                {entry.candidate_id}
              </Typography>
              <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>
                {entry.text}
              </Typography>
            </Box>
          ))}

          {narrative.limitations_summary && (
            <Box sx={{ mt: 2 }}>
              <SectionTitle>Limitazioni</SectionTitle>
              <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                {narrative.limitations_summary}
              </Typography>
            </Box>
          )}

          {narrative.closing_note && (
            <Typography sx={{
              fontFamily: font.body, fontSize: 12, color: color.slate, mt: 1.5, fontStyle: 'italic',
            }}>
              {narrative.closing_note}
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
