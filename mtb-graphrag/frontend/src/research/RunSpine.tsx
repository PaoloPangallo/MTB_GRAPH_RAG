/**
 * La spina della run: i 15 stage come sequenza verticale.
 *
 * È l'elemento firma della console, e il suo compito non è decorare ma
 * codificare la distinzione su cui l'intera architettura è costruita: ciò che
 * il grafo *propone* contro ciò che un documento *prova*.
 *
 * Il marcatore lo dice senza colore: pieno quando lo stage ha prodotto un
 * risultato, cavo quando non è stato eseguito, sbarrato quando si è fermato. Il
 * filetto verticale collega gli stage eseguiti e si interrompe dove la pipeline
 * si è fermata, così la lunghezza della spina è già l'informazione.
 *
 * La numerazione 01–15 è giustificata: qui l'ordine è reale e portante, non
 * un ornamento.
 */

import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { color, font, formatDuration, reasonLabel, stageStatusStyle } from './tokens';
import { STAGE_LABELS, TERM_TOOLTIPS, type PipelineStage } from './types';

interface RunSpineProps {
  stages: PipelineStage[];
  selectedStageId: string | null;
  onSelect: (stageId: string) => void;
}

function Marker({ variant, tone }: { variant: 'filled' | 'hollow' | 'barred'; tone: string }) {
  const common = {
    width: 11,
    height: 11,
    borderRadius: '50%',
    border: `1.5px solid ${tone}`,
    flexShrink: 0,
  } as const;

  if (variant === 'filled') return <Box aria-hidden sx={{ ...common, backgroundColor: tone }} />;
  if (variant === 'hollow') return <Box aria-hidden sx={{ ...common, backgroundColor: color.canvas }} />;
  return (
    <Box aria-hidden sx={{ ...common, backgroundColor: color.canvas, position: 'relative',
      '&::after': {
        content: '""', position: 'absolute', left: -3, right: -3, top: '50%',
        height: '1.5px', backgroundColor: tone,
      } }} />
  );
}

export default function RunSpine({ stages, selectedStageId, onSelect }: RunSpineProps) {
  if (stages.length === 0) {
    return (
      <Typography sx={{ fontFamily: font.body, color: color.muted, py: 4 }}>
        Nessuna run in corso. Scegli un caso per avviare la pipeline.
      </Typography>
    );
  }

  return (
    <Box component="ol" aria-label="Stage della pipeline" sx={{ listStyle: 'none', m: 0, p: 0 }}>
      {stages.map((stage, index) => {
        const style = stageStatusStyle[stage.status] ?? stageStatusStyle.PENDING;
        const isLLM = stage.producer.kind === 'LLM';
        const isSelected = stage.stage_id === selectedStageId;
        const replayed = Boolean((stage.output_preview as { replayed?: boolean }).replayed);
        const isLast = index === stages.length - 1;

        return (
          <Box component="li" key={stage.stage_id} sx={{ position: 'relative' }}>
            {/* Filetto di collegamento: si spegne dopo l'ultimo stage eseguito. */}
            {!isLast && (
              <Box aria-hidden sx={{
                position: 'absolute', left: 25, top: 26, bottom: -2, width: '1.5px',
                backgroundColor: stage.status === 'SKIPPED' ? 'transparent' : color.hairline,
                borderLeft: stage.status === 'SKIPPED' ? `1.5px dashed ${color.hairline}` : 'none',
              }} />
            )}

            <Box
              component="button"
              type="button"
              onClick={() => onSelect(stage.stage_id)}
              aria-current={isSelected ? 'true' : undefined}
              // Il contenuto è frammentato fra numero, marcatore, titolo e
              // badge: senza un nome esplicito il controllo arriva muto allo
              // screen reader, come verificato leggendo l'albero accessibile.
              aria-label={`Stage ${stage.sequence}, ${STAGE_LABELS[stage.stage_id] ?? stage.stage_id}, ${style.label}`}
              sx={{
                display: 'flex', alignItems: 'flex-start', gap: 1.5, width: '100%',
                textAlign: 'left', background: isSelected ? color.stone : 'transparent',
                border: 'none', borderBottom: `1px solid ${color.hairline}`,
                px: 1.5, py: 1.75, cursor: 'pointer', font: 'inherit',
                '&:hover': { background: isSelected ? color.stone : '#fafafa' },
                '&:focus-visible': { outline: `2px solid ${color.focus}`, outlineOffset: -2 },
              }}
            >
              <Typography component="span" sx={{
                fontFamily: font.mono, fontSize: 12, color: color.muted,
                width: 20, pt: '1px', flexShrink: 0,
              }}>
                {String(stage.sequence).padStart(2, '0')}
              </Typography>

              <Box sx={{ pt: '3px' }}><Marker variant={style.marker} tone={style.fg} /></Box>

              <Box sx={{ minWidth: 0, flex: 1 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                  <Typography component="span" sx={{
                    fontFamily: font.body, fontSize: 15, fontWeight: 500,
                    color: stage.status === 'SKIPPED' ? color.muted : color.ink,
                  }}>
                    {STAGE_LABELS[stage.stage_id] ?? stage.stage_id}
                  </Typography>

                  {isLLM && (
                    <Tooltip title={TERM_TOOLTIPS.llm}>
                      <Chip label="LLM" size="small" sx={{
                        height: 18, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
                        color: '#8a3a22', backgroundColor: color.coralSoft, borderRadius: '4px',
                      }} />
                    </Tooltip>
                  )}

                  {replayed && (
                    <Tooltip title={TERM_TOOLTIPS.replayed}>
                      <Chip label="REPLAY" size="small" sx={{
                        height: 18, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
                        color: color.slate, backgroundColor: color.stone, borderRadius: '4px',
                      }} />
                    </Tooltip>
                  )}
                </Stack>

                <Stack direction="row" spacing={1.5} sx={{ mt: 0.25, flexWrap: "wrap" }}>
                  {/* Lo stato è sempre testuale: mai indicato dal solo colore. */}
                  <Typography component="span" sx={{ fontFamily: font.body, fontSize: 12, color: style.fg }}>
                    {style.label}
                  </Typography>
                  <Typography component="span" sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                    {formatDuration(stage.duration_ms)}
                  </Typography>
                  {!isLLM && (
                    <Typography component="span" sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                      deterministico
                    </Typography>
                  )}
                </Stack>

                {stage.reason_codes.length > 0 && (
                  <Typography sx={{ mt: 0.5, fontFamily: font.body, fontSize: 12, color: color.slate }}>
                    {stage.reason_codes.map(reasonLabel).join(' · ')}
                  </Typography>
                )}
              </Box>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
