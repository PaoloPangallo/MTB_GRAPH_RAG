/**
 * Intestazione operativa: la prima cosa che si legge di una run.
 *
 * Prima rispondeva a «in quale modalità è stata eseguita». La domanda non
 * esiste più — il runtime è uno solo — e al suo posto ci sono le domande che
 * restano davvero aperte a run conclusa: da dove sono arrivati i documenti,
 * quanti sono stati letti dalla cache e quanti acquisiti da un'API, se qualcuno
 * è degradato ad abstract, quante volte è stato chiamato il modello, e se la
 * pipeline si è arrestata.
 *
 * Nessun valore qui viene calcolato nel browser: `document_acquisition` arriva
 * dal backend, che lo deriva dallo stage 6. Ricalcolarlo qui creerebbe una
 * seconda definizione di «il documento è stato preso da qui» accanto a quella
 * dello stage che l'ha davvero preso.
 *
 * Le etichette storiche — `execution_mode`, `replay_artifacts_used` — compaiono
 * **solo** su una run archiviata che le renda diverse dal caso canonico. Su una
 * run canonica varrebbero sempre `LIVE` e `0`, e un campo che dice sempre la
 * stessa cosa non informa: occupa spazio e riporta in vista un concetto che
 * l'architettura ha smesso di avere.
 */

import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { PIPELINE_ABORT_LABEL, color, font, radius, reasonLabel, runModeStyle } from './tokens';
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

/**
 * Come sono arrivati i documenti, in una riga.
 *
 * `null` significa «non misurato» e viene reso come tale: lo stage documentale
 * non è stato raggiunto, e uno zero direbbe un'altra cosa.
 */
function acquisitionLabel(acquisition: PipelineRun['document_acquisition']): string {
  if (!acquisition?.executed) return 'non raggiunta';
  const parts: string[] = [];
  if (acquisition.cache_hits) parts.push(`${acquisition.cache_hits} da cache`);
  if (acquisition.network_fetches) parts.push(`${acquisition.network_fetches} da API`);
  if (acquisition.documents_unavailable) {
    parts.push(`${acquisition.documents_unavailable} non disponibili`);
  }
  return parts.length > 0 ? parts.join(' · ') : 'nessun documento';
}

export default function RunModeHeader({ run }: RunModeHeaderProps) {
  if (!run) return null;

  const cache = run.document_cache ?? { document_cache_available: false };
  const cacheAvailable = Boolean(cache.document_cache_available);
  const acquisition = run.document_acquisition;
  const degraded = acquisition?.degraded_to_abstract ?? 0;

  // Un arresto è un esito terminale della catena documentale, non un guasto del
  // trasporto: si legge accanto all'acquisizione, dove sta la sua causa.
  const aborted = run.status === 'FAILED' && Boolean(run.stopped_at);

  // Le etichette storiche hanno qualcosa da dire solo se differiscono dal caso
  // canonico. Su ogni altra run restano invisibili.
  const replayUsed = run.replay_artifacts_used ?? 0;
  const isHistorical = run.execution_mode !== 'LIVE' || replayUsed > 0;
  const historicalStyle = runModeStyle[run.execution_mode] ?? runModeStyle.REPLAY;

  return (
    <Box
      data-testid="run-mode-header"
      sx={{
        border: `1px solid ${aborted ? '#e8c2c2' : color.borderLight}`,
        borderRadius: `${radius.sm}px`,
        backgroundColor: aborted ? '#fdf6f6' : '#fbfbfa',
        px: 2.5, py: 2, mb: 3,
      }}
    >
      <Stack direction="row" spacing={4} sx={{ flexWrap: 'wrap', rowGap: 2 }}>
        <Field label="Document acquisition" tone={acquisition?.executed ? color.ink : color.muted}>
          <Box component="span" data-testid="document-acquisition">
            {acquisitionLabel(acquisition)}
          </Box>
        </Field>

        <Field label="Document cache" tone={cacheAvailable ? color.ink : color.error}>
          <Box component="span" data-testid="document-cache">
            {cacheAvailable ? 'AVAILABLE' : 'UNAVAILABLE'}
          </Box>
        </Field>

        {degraded > 0 && (
          <Field label="Degraded to abstract" tone="#8a4b2f">
            <Tooltip title={TERM_TOOLTIPS.degraded_to_abstract}>
              <Box component="span" data-testid="degraded-to-abstract">{degraded}</Box>
            </Tooltip>
          </Field>
        )}

        <Field label="LLM calls">
          <Box component="span" data-testid="llm-calls">{run.llm_calls ?? 0}</Box>
        </Field>

        {aborted && (
          <Box sx={{ alignSelf: 'center' }}>
            <Tooltip title={reasonLabel(run.stopped_at ?? '')}>
              <Chip
                label={PIPELINE_ABORT_LABEL}
                size="small"
                data-testid="pipeline-abort"
                sx={{
                  height: 22, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
                  color: color.error, backgroundColor: '#fdf0f0', borderRadius: '6px',
                }}
              />
            </Tooltip>
          </Box>
        )}
      </Stack>

      {acquisition?.executed && acquisition.sources.length > 0 && (
        <Stack direction="row" spacing={2} sx={{ mt: 1.5, flexWrap: 'wrap', rowGap: 0.5 }}>
          <Typography data-testid="document-sources" sx={{
            fontFamily: font.mono, fontSize: 11, color: color.slate,
          }}>
            fonti: {acquisition.sources.join(' · ')}
          </Typography>
        </Stack>
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

      {/* Run archiviata prodotta quando esistevano due modalità. I suoi metadati
          restano leggibili — nasconderli renderebbe una vecchia run REPLAY
          indistinguibile da una canonica — ma sono dichiarati come storici e non
          come una scelta ancora disponibile. */}
      {isHistorical && (
        <Box
          data-testid="historical-run-metadata"
          sx={{ mt: 2, pt: 1.5, borderTop: `1px solid ${color.hairline}` }}
        >
          <Typography sx={{
            fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
            textTransform: 'uppercase', color: color.muted, mb: 0.5,
          }}>
            Historical run metadata
          </Typography>
          <Typography sx={{ fontFamily: font.body, fontSize: 13, color: historicalStyle.fg }}>
            <Box component="span" data-testid="historical-execution-mode">
              {historicalStyle.label}
            </Box>
            {replayUsed > 0 && (
              <>
                {' · '}
                <Box component="span" data-testid="replay-artifacts-used">{replayUsed}</Box>
                {replayUsed === 1 ? ' artefatto registrato' : ' artefatti registrati'}
              </>
            )}
          </Typography>
          <Typography sx={{ mt: 0.5, fontFamily: font.body, fontSize: 12, color: color.slate }}>
            Run prodotta da infrastruttura di riproduzione storica. Non è una
            modalità selezionabile del runtime.
          </Typography>
        </Box>
      )}
    </Box>
  );
}
