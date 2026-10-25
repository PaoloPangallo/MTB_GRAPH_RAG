/**
 * Ispezione di un singolo stage.
 *
 * Mostra ciò che il backend ha prodotto e nient'altro: non ricalcola status,
 * non deriva gate, non interpreta. Il JSON è redatto alla fonte, quindi ciò che
 * si vede qui è esattamente ciò che è entrato nel ledger.
 */

import { useState } from 'react';
import { Box, Chip, Stack, Tab, Tabs, Typography } from '@mui/material';
import StageOutput from './stages';
import { stageTiming } from './stageTiming';
import StructuredValue, { JsonInspector } from './values/StructuredValue';
import { color, font, formatDuration, reasonLabel, stageStatusStyle } from './tokens';
import { STAGE_LABELS, type PipelineEvent, type PipelineStage } from './types';

interface StageInspectorProps {
  stage: PipelineStage | null;
  events: PipelineEvent[];
  clinicalText?: string;
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{
      fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
      textTransform: 'uppercase', color: color.muted, mb: 0.5,
    }}>
      {children}
    </Typography>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: { xs: 0.5, sm: 2 }, py: 1, borderBottom: `1px solid ${color.hairline}` }}>
      <Typography sx={{
        fontFamily: font.body, fontSize: 13, color: color.slate,
        width: 168, flexShrink: 0,
      }}>
        {label}
      </Typography>
      <Box sx={{ minWidth: 0, flex: 1 }}>{children}</Box>
    </Box>
  );
}

function Value({ children }: { children: React.ReactNode }) {
  return <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>{children}</Typography>;
}

function Mono({ children }: { children: React.ReactNode }) {
  return <Typography sx={{ fontFamily: font.mono, fontSize: 12, color: color.body, wordBreak: 'break-all' }}>{children}</Typography>;
}

export default function StageInspector({ stage, events, clinicalText }: StageInspectorProps) {
  const [tab, setTab] = useState(0);

  if (!stage) {
    return (
      <Box sx={{ p: 4 }}>
        <Typography sx={{ fontFamily: font.body, color: color.muted }}>
          Scegli uno stage nella spina per ispezionarlo.
        </Typography>
      </Box>
    );
  }

  const style = stageStatusStyle[stage.status] ?? stageStatusStyle.PENDING;
  const isLLM = stage.producer.kind === 'LLM';
  const timing = stageTiming(stage);

  return (
    <Box>
      <Box sx={{ px: 3, pt: 3, pb: 2 }}>
        <Label>Stage {String(stage.sequence).padStart(2, '0')}</Label>
        <Typography sx={{
          fontFamily: font.display, fontSize: 30, lineHeight: 1.05,
          letterSpacing: '-0.02em', color: color.ink,
        }}>
          {STAGE_LABELS[stage.stage_id] ?? stage.stage_id}
        </Typography>

        <Stack direction="row" spacing={1.5} sx={{ mt: 1.5, alignItems: 'center', flexWrap: "wrap" }}>
          <Chip label={style.label} size="small" sx={{
            height: 22, fontFamily: font.body, fontSize: 12,
            color: style.fg, backgroundColor: style.bg === 'transparent' ? color.stone : style.bg,
            borderRadius: '6px',
          }} />
          <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
            {isLLM ? `LLM · ${stage.producer.model ?? 'modello non disponibile'}` : 'deterministico'}
          </Typography>
        </Stack>
      </Box>

      <Tabs
        value={tab}
        onChange={(_, next: number) => setTab(next)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ px: 2, borderBottom: `1px solid ${color.hairline}`, minHeight: 40 }}
      >
        <Tab label="Sintesi" />
        <Tab label="Output" />
        <Tab label="JSON" />
        <Tab label="Provenienza" />
        <Tab label={`Eventi (${events.length})`} />
      </Tabs>

      <Box sx={{ px: 3, py: 2 }}>
        {tab === 0 && (
          <Box>
            <Row label="Stato"><Value>{style.label}</Value></Row>
            <Row label={timing.label}><Mono>{formatDuration(timing.milliseconds)}</Mono></Row>
            <Row label="Componente"><Mono>{stage.producer.component}</Mono></Row>
            <Row label="Versione"><Mono>{stage.producer.version}</Mono></Row>
            {Object.keys(stage.metrics ?? {}).length > 0 && <Row label="Metriche registrate"><StructuredValue value={stage.metrics} /></Row>}
            {isLLM && (
              <>
                <Row label="Modello"><Mono>{stage.producer.model ?? 'non disponibile'}</Mono></Row>
                <Row label="Prompt version"><Mono>{stage.producer.prompt_version ?? 'non disponibile'}</Mono></Row>
                {stage.producer.transport_version && (
                  <Row label="Transport version"><Mono>{stage.producer.transport_version}</Mono></Row>
                )}
              </>
            )}
            {stage.reason_codes.length > 0 && (
              <Row label="Motivazione">
                <Stack spacing={0.5}>
                  {stage.reason_codes.map((code) => (
                    <Box key={code}>
                      <Value>{reasonLabel(code)}</Value>
                      <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>{code}</Typography>
                    </Box>
                  ))}
                </Stack>
              </Row>
            )}
            {stage.warnings.length > 0 && (
              <Row label="Avvisi">
                <Stack spacing={0.5}>
                  {stage.warnings.map((w) => <Value key={w}>{reasonLabel(w)}</Value>)}
                </Stack>
              </Row>
            )}
            {stage.errors.length > 0 && (
              <Row label="Errori">
                <Stack spacing={0.5}>
                  {stage.errors.map((e) => (
                    <Typography key={e} sx={{ fontFamily: font.body, fontSize: 13, color: color.error }}>{e}</Typography>
                  ))}
                </Stack>
              </Row>
            )}
            {stage.producer.kind === 'DETERMINISTIC' && (
              <Typography sx={{ mt: 2, fontFamily: font.body, fontSize: 12, color: color.slate }}>
                Producer dichiarato dal runtime: codice deterministico. Gli input possono
                provenire da stage LLM; la verifica della relazione può includere un confronto semantico indipendente.
              </Typography>
            )}
          </Box>
        )}

        {/* La vista dedicata allo stage. Il JSON grezzo resta a un tab di
            distanza: serve a verificare che la resa non aggiunga nulla. */}
        {tab === 1 && <StageOutput stage={stage} clinicalText={clinicalText} />}

        {tab === 2 && <JsonInspector value={stage.output_preview} />}

        {tab === 3 && (
          <Box>
            <Row label="Stage"><Mono>{stage.stage_id}</Mono></Row>
            <Row label="Tipo"><Mono>{stage.stage_type}</Mono></Row>
            <Row label="Sequenza"><Mono>{stage.sequence}</Mono></Row>
            <Row label="Producer"><Mono>{stage.producer.kind}</Mono></Row>
            {Object.keys(stage.lineage).length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Label>Lineage</Label>
                <StructuredValue value={stage.lineage} />
              </Box>
            )}
          </Box>
        )}

        {tab === 4 && (
          <Stack spacing={1}>
            {events.length === 0 && (
              <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.muted }}>
                Nessun evento registrato per questo stage.
              </Typography>
            )}
            {events.map((event) => (
              <Box key={event.event_id} sx={{
                border: `1px solid ${color.borderLight}`, borderRadius: '8px', p: 1.5,
              }}>
                <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                  <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                    #{event.sequence}
                  </Typography>
                  <Typography sx={{ fontFamily: font.mono, fontSize: 12, color: color.ink }}>
                    {event.event_type}
                  </Typography>
                  <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
                    {event.created_at}
                  </Typography>
                </Stack>
                {event.payload_hash && (
                  <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, mt: 0.5 }}>
                    payload sha256 {event.payload_hash.slice(0, 16)}…
                  </Typography>
                )}
              </Box>
            ))}
          </Stack>
        )}
      </Box>
    </Box>
  );
}
