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
import StructuredValue from './values/StructuredValue';
import { color, font, radius } from './tokens';
import { TERM_TOOLTIPS, type ProvenanceItem, type ProvenanceLevel } from './types';

const LEVEL_LABELS: Record<string, string> = {
  CASE_CONTEXT: 'CaseContext',
  GRAPH_CANDIDATE_ASSERTION: 'Graph Candidate Assertion',
  DOCUMENT: 'Documento',
  SOURCE_UNIT: 'Source Unit',
  AUTHOR_QUOTE: 'Citazione d’autore',
  ENRICHMENT_VALIDATION: 'Validazione della citazione',
  DETERMINISTIC_CHECK: 'Controlli deterministici',
  GATE_AND_STATUS: 'Gate e status',
  DOSSIER_ITEM: 'Voce del dossier',
};

/**
 * Riferimento di un livello.
 *
 * Un identificatore è una stringa e va reso come tale; una voce di dossier è un
 * oggetto, e serializzarla su una riga la rendeva illeggibile proprio nel punto
 * in cui la catena arriva al risultato. Gli oggetti passano quindi al renderer
 * strutturato.
 */
function LevelRef({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <Mono>non disponibile</Mono>;
  }
  if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
    return <Mono>{value.length ? value.join(', ') : 'nessuno'}</Mono>;
  }
  if (typeof value === 'object') {
    return <Box sx={{ mt: 0.5 }}><StructuredValue value={value} /></Box>;
  }
  return <Mono>{String(value)}</Mono>;
}

function Mono({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted, mt: 0.25 }}>
      {children}
    </Typography>
  );
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

      {level.ref !== undefined && <LevelRef value={level.ref} />}

      {/* Le citazioni sono il punto in cui la catena tocca un documento: vanno
          mostrate qui, separando ciò che è stato ammesso da ciò che non lo è. */}
      {level.level === 'AUTHOR_QUOTE' && (
        <Box sx={{ mt: 0.75 }}>
          {(level.accepted_quotes ?? []).map((quote, i) => (
            <Box key={`ok-${i}`} sx={{ mb: 1 }}>
              <Typography sx={{
                fontFamily: font.body, fontSize: 13, color: color.ink,
                borderLeft: `2px solid ${color.coral}`, pl: 1.5, fontStyle: 'italic',
              }}>
                “{String(quote.author_claim_quote ?? '')}”
              </Typography>
              <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, pl: 1.5 }}>
                {String(quote.source_unit_id ?? '—')} · {String(quote.paper_id ?? '—')}
              </Typography>
            </Box>
          ))}
          {(level.rejected_quotes ?? []).map((quote, i) => (
            <Typography key={`ko-${i}`} sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
              Citazione rigettata, visibile per audit e non nel dossier — {String(quote.paper_id ?? '—')}
            </Typography>
          ))}
          {(level.abstentions ?? []).map((entry, i) => (
            <Typography key={`ab-${i}`} sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
              Astensione — {String(entry.abstention_reason ?? 'nessuna frase letterale a supporto')}
            </Typography>
          ))}
          {(level.accepted_quotes ?? []).length === 0
            && (level.rejected_quotes ?? []).length === 0
            && (level.abstentions ?? []).length === 0 && (
            <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.muted }}>
              Nessuna citazione: l’enricher non è stato chiamato per questa candidate.
            </Typography>
          )}
        </Box>
      )}

      {level.level === 'ENRICHMENT_VALIDATION' && (
        <Stack direction="row" spacing={0.5} sx={{ mt: 0.75, flexWrap: 'wrap', rowGap: 0.5 }}>
          {(level.validations ?? []).map((validation, i) => (
            <Chip key={i} label={String(validation.outcome ?? 'ignoto')} size="small" sx={{
              height: 18, fontFamily: font.mono, fontSize: 9,
              backgroundColor: color.stone, color: color.body, borderRadius: '4px',
            }} />
          ))}
          {(level.validations ?? []).length === 0 && (
            <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.muted }}>
              Nessuna validazione
            </Typography>
          )}
        </Stack>
      )}

      {level.level === 'DETERMINISTIC_CHECK' && (
        <Stack direction="row" spacing={0.5} sx={{ mt: 0.75, flexWrap: 'wrap', rowGap: 0.5 }}>
          {(level.checks ?? [])
            .filter((check) => check.source === 'COMPUTED_HERE' || check.source === 'INHERITED_VERIFIED_RESULT')
            .map((check, i) => (
              <Tooltip key={i} title={`origine: ${String(check.source)} · stage: ${String(check.source_stage ?? '—')}`}>
                <Chip
                  label={`${String(check.check_id)}: ${String(check.result ?? '—')}`}
                  size="small"
                  sx={{
                    height: 18, fontFamily: font.mono, fontSize: 9,
                    backgroundColor: check.source === 'COMPUTED_HERE' ? '#edfce9' : color.stone,
                    color: color.body, borderRadius: '4px',
                  }}
                />
              </Tooltip>
            ))}
        </Stack>
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
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1.5 }}>
            <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>
              {item.candidate_id}
            </Typography>
            {/* Senza citazione accettata la candidate resta sostenuta dal solo
                grafo. Etichettarla è ciò che impedisce di leggerla come prova. */}
            <Tooltip
              title={item.document_grounded
                ? 'Una citazione verificata ancora questa candidate a un documento.'
                : 'Nessuna citazione accettata: la candidate è sostenuta solo dal grafo e non è prova documentale.'}
            >
              <Chip
                label={item.provenance_level ?? (item.document_grounded ? 'DOCUMENT_GROUNDED' : 'PARENT_LEVEL_ONLY')}
                size="small"
                sx={{
                  height: 18, fontFamily: font.mono, fontSize: 9, letterSpacing: '0.06em',
                  backgroundColor: item.document_grounded ? '#edfce9' : color.stone,
                  color: item.document_grounded ? color.deepGreen : color.slate,
                  borderRadius: '4px',
                }}
              />
            </Tooltip>
          </Stack>
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
