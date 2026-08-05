/**
 * La catena di provenienza: dal CaseContext al gate, un livello per riga.
 *
 * Due etichette sono obbligatorie e vengono dai dati, non da questa vista:
 * una candidate del grafo porta `graph_derived` con `documentary_proof: false`,
 * e al livello Source Unit il testo è **sempre** assente. Quest'ultima non è
 * una scelta di presentazione: l'indice contiene solo locatori e
 * `content_hash`, e il testo del documento non transita mai per l'API.
 */

import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { color, font, radius } from './tokens';
import { TERM_TOOLTIPS, type ProvenanceItem, type ProvenanceLevel } from './types';

const LEVEL_LABELS: Record<string, string> = {
  CASE_CONTEXT: 'CaseContext',
  GRAPH_CANDIDATE_ASSERTION: 'Graph Candidate Assertion',
  DOCUMENT: 'Documento',
  SOURCE_UNIT: 'Source Unit',
  AUTHOR_QUOTE: 'Citazione d’autore',
  VALIDATION: 'Validazione',
  GATE_AND_STATUS: 'Gate e status',
  DOSSIER_ITEM: 'Voce del dossier',
};

function refToText(ref: unknown): string {
  if (ref === null || ref === undefined) return 'non disponibile';
  if (Array.isArray(ref)) return ref.length ? ref.join(', ') : 'nessuno';
  if (typeof ref === 'object') return JSON.stringify(ref);
  return String(ref);
}

function Level({ level, isLast }: { level: ProvenanceLevel; isLast: boolean }) {
  const units = level.units ?? [];

  return (
    <Box component="li" sx={{ position: 'relative', pl: 3, pb: isLast ? 0 : 2 }}>
      {!isLast && (
        <Box aria-hidden sx={{
          position: 'absolute', left: 4, top: 14, bottom: 0,
          width: '1.5px', backgroundColor: color.hairline,
        }} />
      )}
      <Box aria-hidden sx={{
        position: 'absolute', left: 0, top: 6, width: 9, height: 9,
        borderRadius: '50%', border: `1.5px solid ${color.ink}`,
        backgroundColor: level.level === 'SOURCE_UNIT' ? color.canvas : color.ink,
      }} />

      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography sx={{ fontFamily: font.body, fontSize: 14, fontWeight: 500, color: color.ink }}>
          {LEVEL_LABELS[level.level] ?? level.level}
        </Typography>

        {level.graph_derived && (
          <Tooltip title={TERM_TOOLTIPS.graph_derived}>
            <Chip label="GRAPH-DERIVED" size="small" sx={{
              height: 18, fontFamily: font.mono, fontSize: 9, letterSpacing: '0.06em',
              backgroundColor: color.stone, color: color.slate, borderRadius: '4px',
            }} />
          </Tooltip>
        )}
        {level.documentary_proof === false && (
          <Typography sx={{ fontFamily: font.body, fontSize: 11, color: color.slate }}>
            non è prova documentale
          </Typography>
        )}
        {level.replayed && (
          <Tooltip title={TERM_TOOLTIPS.replayed}>
            <Chip label="REPLAY" size="small" sx={{
              height: 18, fontFamily: font.mono, fontSize: 9, letterSpacing: '0.06em',
              backgroundColor: color.stone, color: color.slate, borderRadius: '4px',
            }} />
          </Tooltip>
        )}
      </Stack>

      {level.ref !== undefined && (
        <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted, mt: 0.25 }}>
          {refToText(level.ref)}
        </Typography>
      )}

      {level.level === 'SOURCE_UNIT' && (
        <Box sx={{ mt: 0.75 }}>
          <Typography sx={{ fontFamily: font.body, fontSize: 11, color: color.slate }}>
            {units.length} source unit · solo locatori e hash, nessun testo del documento
          </Typography>
          {units.slice(0, 4).map((unit, i) => (
            <Typography key={i} sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
              {String(unit.source_unit_id ?? '—')} · {String(unit.section ?? '—')} ·{' '}
              {String(unit.char_start ?? '—')}–{String(unit.char_end ?? '—')}
            </Typography>
          ))}
          {units.length > 4 && (
            <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
              … altre {units.length - 4}
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
}

export default function ProvenanceTree({ items }: { items: ProvenanceItem[] }) {
  if (items.length === 0) {
    return (
      <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.muted, py: 3 }}>
        Nessuna catena di provenienza: la run non ha prodotto candidate.
      </Typography>
    );
  }

  return (
    <Box>
      {items.map((item) => (
        <Box key={item.candidate_id} sx={{
          border: `1px solid ${color.borderLight}`, borderRadius: `${radius.md}px`,
          p: 2.5, mb: 2,
        }}>
          <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted, mb: 1.5 }}>
            {item.candidate_id}
          </Typography>
          <Box component="ol" aria-label={`Catena di provenienza per ${item.candidate_id}`}
               sx={{ listStyle: 'none', m: 0, p: 0 }}>
            {item.chain.map((level, index) => (
              <Level key={`${level.level}-${index}`} level={level}
                     isLast={index === item.chain.length - 1} />
            ))}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
