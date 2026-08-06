/**
 * Intestazione di modalità: la prima cosa che si legge di una run.
 *
 * Risponde a quattro domande prima di ogni altra, perché sono quelle che
 * determinano come va letto tutto il resto: è stata eseguita ora, la cache
 * documentale c'era, quante volte è stato chiamato il modello, e quanti
 * artefatti registrati sono stati usati.
 *
 * `Replay artifacts used` è mostrato **sempre**, anche quando vale zero. Uno
 * zero visibile è un'affermazione verificabile; un campo che compare solo
 * quando è diverso da zero lascia il lettore senza modo di distinguere "nessun
 * artefatto" da "non misurato".
 *
 * Nessun valore qui viene calcolato nel browser: `execution_mode`, `fully_live`
 * e `replay_artifacts_used` arrivano dal backend, che li deriva dalle origini
 * degli stage. Ricalcolarli qui creerebbe una seconda definizione di "live".
 */

import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { color, font, radius, runModeStyle } from './tokens';
import { TERM_TOOLTIPS, type PipelineRun } from './types';

interface RunModeHeaderProps {
  run: PipelineRun | null;
}

function Field({ label, children, tone }: {
  label: string;
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <Box sx={{ minWidth: 132 }}>
      <Typography sx={{
        fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
        textTransform: 'uppercase', color: color.muted,
      }}>
        {label}
      </Typography>
      <Typography sx={{
        fontFamily: font.body, fontSize: 15, color: tone ?? color.ink, mt: 0.25,
      }}>
        {children}
      </Typography>
    </Box>
  );
}

export default function RunModeHeader({ run }: RunModeHeaderProps) {
  if (!run) return null;

  const mode = runModeStyle[run.execution_mode] ?? runModeStyle.REPLAY;
  const cache = run.document_cache ?? { document_cache_available: false };
  const replayUsed = run.replay_artifacts_used ?? 0;
  const cacheAvailable = Boolean(cache.document_cache_available);

  return (
    <Box
      data-testid="run-mode-header"
      sx={{
        border: `1px solid ${replayUsed > 0 ? '#e2c9bd' : color.borderLight}`,
        borderRadius: `${radius.sm}px`, backgroundColor: mode.bg, px: 2.5, py: 2, mb: 3,
      }}
    >
      <Stack direction="row" spacing={4} sx={{ flexWrap: 'wrap', rowGap: 2 }}>
        <Field label="Execution mode" tone={mode.fg}>
          <Tooltip title={run.execution_mode === 'HYBRID' ? TERM_TOOLTIPS.hybrid : TERM_TOOLTIPS.live}>
            <Box component="span" data-testid="execution-mode">{mode.label}</Box>
          </Tooltip>
          {run.requested_mode !== run.execution_mode && (
            <Typography component="span" sx={{
              ml: 1, fontFamily: font.mono, fontSize: 11, color: color.slate,
            }}>
              richiesta {run.requested_mode}
            </Typography>
          )}
        </Field>

        <Field
          label="Document cache"
          tone={cacheAvailable ? color.ink : color.error}
        >
          <Box component="span" data-testid="document-cache">
            {cacheAvailable ? 'AVAILABLE' : 'UNAVAILABLE'}
          </Box>
        </Field>

        <Field label="LLM calls">
          <Box component="span" data-testid="llm-calls">{run.llm_calls ?? 0}</Box>
        </Field>

        <Field label="Replay artifacts used" tone={replayUsed > 0 ? '#8a4b2f' : color.ink}>
          <Box component="span" data-testid="replay-artifacts-used">{replayUsed}</Box>
        </Field>

        {run.fully_live && (
          <Box sx={{ alignSelf: 'center' }}>
            <Tooltip title={TERM_TOOLTIPS.fully_live}>
              <Chip
                label="FULLY LIVE"
                size="small"
                data-testid="fully-live-badge"
                sx={{
                  height: 22, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
                  color: '#0b5c3f', backgroundColor: '#d6ecdf', borderRadius: '6px',
                }}
              />
            </Tooltip>
          </Box>
        )}
      </Stack>

      {/* Una run con artefatti registrati non può essere etichettata FULLY LIVE:
          la ragione va detta, non solo il fatto. */}
      {replayUsed > 0 && (
        <Typography sx={{ mt: 1.5, fontFamily: font.body, fontSize: 13, color: '#8a4b2f' }}>
          {replayUsed} stage {replayUsed === 1 ? 'ha usato un artefatto registrato' : 'hanno usato artefatti registrati'}:
          {' '}questa run non è completamente live.
        </Typography>
      )}

      {cacheAvailable && (
        <Stack direction="row" spacing={2} sx={{ mt: 1.5, flexWrap: 'wrap', rowGap: 0.5 }}>
          {[
            ['cache', cache.cache_path_redacted],
            ['versione', cache.cache_version],
            ['manifest', cache.manifest_hash ? `${cache.manifest_hash.slice(0, 12)}…` : null],
            ['documenti', cache.document_count],
            ['source unit', cache.source_unit_count],
          ]
            .filter(([, value]) => value !== null && value !== undefined)
            .map(([label, value]) => (
              <Typography key={String(label)} sx={{
                fontFamily: font.mono, fontSize: 11, color: color.slate,
              }}>
                {label}: {String(value)}
              </Typography>
            ))}
        </Stack>
      )}

      {run.rehydrated && (
        <Typography sx={{ mt: 1.5, fontFamily: font.body, fontSize: 13, color: color.slate }}>
          Run ricostruita dal registro degli eventi
          {run.hash_chain_valid === true && ' · catena di hash verificata'}
          {run.recovery_status === 'RECOVERED_INCOMPLETE'
            && ' · interrotta prima della conclusione: gli stage mostrati sono quelli effettivamente registrati'}
        </Typography>
      )}
    </Box>
  );
}
