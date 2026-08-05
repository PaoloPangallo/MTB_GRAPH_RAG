/**
 * Modalità relatore: tutto ciò che serve a verificare, senza aprire la console
 * del browser.
 *
 * Le metriche mostrate qui sono quelle **canoniche**, calcolate dal backend. I
 * conteggi derivati nel browser vivono altrove e sono etichettati come tali: la
 * distinzione va mantenuta visibile, altrimenti un'aggregazione di comodo
 * finisce per essere letta come una misura del sistema.
 *
 * Un valore mancante si legge "non disponibile" e mai zero. Il pilot non
 * registra i token per ogni stage: renderli `0` significherebbe dichiarare una
 * misura che nessuno ha preso.
 */

import { Box, Chip, Stack, Typography } from '@mui/material';
import { color, font, radius } from './tokens';
import type { PipelineEvent, RunMetrics } from './types';

interface SupervisorPanelProps {
  metrics: RunMetrics | null;
  events: PipelineEvent[];
  hashChainValid: boolean | null;
  versions: Record<string, unknown>;
}

function value(raw: number | null | undefined): string {
  return raw === null || raw === undefined ? 'non disponibile' : String(raw);
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ minWidth: 150, py: 1 }}>
      <Typography sx={{
        fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
        textTransform: 'uppercase', color: color.muted,
      }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: font.body, fontSize: 18, color: color.ink }}>
        {children}
      </Typography>
    </Box>
  );
}

export default function SupervisorPanel({
  metrics, events, hashChainValid, versions,
}: SupervisorPanelProps) {
  return (
    <Box>
      {/* Integrità della catena: la proprietà che rende il registro verificabile. */}
      <Box sx={{
        border: `1px solid ${hashChainValid ? color.hairline : color.error}`,
        borderRadius: `${radius.sm}px`, p: 2, mb: 3,
      }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.ink }}>
            Catena di hash{' '}
            {hashChainValid === null
              ? 'non verificata'
              : hashChainValid ? 'verificata' : 'NON valida'}
          </Typography>
          <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
            Registro append-only · {events.length} eventi
          </Typography>
        </Stack>
      </Box>

      <Typography sx={{
        fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
        textTransform: 'uppercase', color: color.muted, mb: 0.5,
      }}>
        Metriche canoniche — calcolate dal backend
      </Typography>
      <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap', mb: 3 }}>
        <Metric label="Durata totale">{value(metrics?.duration_ms_total)} ms</Metric>
        <Metric label="Chiamate LLM">{value(metrics?.llm_calls)}</Metric>
        <Metric label="Token input">{value(metrics?.tokens_input)}</Metric>
        <Metric label="Token output">{value(metrics?.tokens_output)}</Metric>
        <Metric label="Candidate trovate">{value(metrics?.candidates_found)}</Metric>
        <Metric label="Candidate escluse">{value(metrics?.candidates_excluded)}</Metric>
        <Metric label="Quote accettate">{value(metrics?.quotes_accepted)}</Metric>
        <Metric label="Quote rigettate">{value(metrics?.quotes_rejected)}</Metric>
        <Metric label="Astensioni">{value(metrics?.abstentions)}</Metric>
      </Stack>

      {versions && Object.keys(versions).length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography sx={{
            fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
            textTransform: 'uppercase', color: color.muted, mb: 0.75,
          }}>
            Versioni dei componenti
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
            {Object.entries(versions).map(([key, val]) => (
              <Chip key={key} label={`${key}: ${String(val)}`} size="small" sx={{
                height: 20, fontFamily: font.mono, fontSize: 10,
                backgroundColor: color.stone, color: color.body, borderRadius: '4px',
              }} />
            ))}
          </Stack>
        </Box>
      )}

      <Typography sx={{
        fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
        textTransform: 'uppercase', color: color.muted, mb: 0.75,
      }}>
        Registro degli eventi
      </Typography>
      <Box sx={{
        border: `1px solid ${color.borderLight}`, borderRadius: `${radius.sm}px`,
        maxHeight: 420, overflowY: 'auto',
      }}>
        <Box component="table" sx={{ width: '100%', borderCollapse: 'collapse' }}>
          <Box component="tbody">
            {events.map((event) => (
              <Box component="tr" key={event.event_id} sx={{
                borderBottom: `1px solid ${color.hairline}`,
              }}>
                <Box component="td" sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted, p: 1, width: 40 }}>
                  {event.sequence}
                </Box>
                <Box component="td" sx={{ fontFamily: font.mono, fontSize: 11, color: color.ink, p: 1 }}>
                  {event.event_type}
                </Box>
                <Box component="td" sx={{ fontFamily: font.body, fontSize: 11, color: color.slate, p: 1 }}>
                  {event.stage_id ?? '—'}
                </Box>
                <Box component="td" sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, p: 1 }}>
                  {event.producer?.kind ?? '—'}
                </Box>
                <Box component="td" sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, p: 1 }}>
                  {event.payload_hash ? `${event.payload_hash.slice(0, 12)}…` : '—'}
                </Box>
              </Box>
            ))}
            {events.length === 0 && (
              <Box component="tr">
                <Box component="td" sx={{ fontFamily: font.body, fontSize: 13, color: color.muted, p: 2 }}>
                  Nessun evento registrato.
                </Box>
              </Box>
            )}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
