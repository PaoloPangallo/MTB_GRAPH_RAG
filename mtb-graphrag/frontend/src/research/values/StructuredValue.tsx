/**
 * Resa di un valore di forma ignota, senza coercizione a stringa.
 *
 * Gli `output_preview` degli stage sono JSON arbitrario: un CaseContext annidato,
 * una lista di validazioni, una support mask, un intero. Un renderer che facesse
 * `String(value)` produrrebbe `[object Object]` su tutto ciò che non è primitivo
 * — cioè su quasi tutto ciò che conta — e lo stage smetterebbe di essere
 * ispezionabile pur sembrando reso correttamente.
 *
 * Qui la forma decide la resa: primitiva → testo; array di primitive → chip;
 * array di oggetti → tabella; oggetto → coppie chiave/valore, ricorsivamente.
 * Nessun ramo raggiunge `String` su un valore non primitivo.
 */

import { Box, Chip, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { color, font } from '../tokens';

/** Oltre questa profondità si passa a JSON: l'annidamento resterebbe illeggibile. */
const MAX_DEPTH = 4;

type Primitive = string | number | boolean;

function isPrimitive(value: unknown): value is Primitive {
  return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function Absent({ label }: { label: string }) {
  return (
    <Typography component="span" sx={{
      fontFamily: font.body, fontSize: 13, color: color.muted, fontStyle: 'italic',
    }}>
      {label}
    </Typography>
  );
}

function Scalar({ value }: { value: Primitive }) {
  const text = typeof value === 'boolean' ? String(value) : `${value}`;
  // I codici — reason code, id, hash, versioni — si leggono meglio in monospazio
  // e vanno distinti dalla prosa.
  const isCode = typeof value !== 'number'
    && /^[A-Z][A-Z0-9_]{3,}$/.test(text) === false
    && /^(GCA|EB|SU|PMID|DOI|NCT|sha256)/.test(text);
  const isEnum = typeof value === 'string' && /^[A-Z][A-Z0-9_]{2,}$/.test(text);

  if (isEnum) {
    return (
      <Chip label={text} size="small" sx={{
        height: 20, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.04em',
        backgroundColor: color.stone, color: color.body, borderRadius: '4px',
      }} />
    );
  }

  return (
    <Typography component="span" sx={{
      fontFamily: isCode ? font.mono : font.body,
      fontSize: isCode ? 12 : 13,
      color: color.body,
      wordBreak: 'break-word',
    }}>
      {text}
    </Typography>
  );
}

/** Colonne di una tabella di oggetti: l'unione delle chiavi, nell'ordine di comparsa. */
function columnsOf(rows: Array<Record<string, unknown>>): string[] {
  const seen: string[] = [];
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!seen.includes(key)) seen.push(key);
    });
  });
  return seen;
}

function ArrayTable({ rows, depth }: { rows: Array<Record<string, unknown>>; depth: number }) {
  const columns = columnsOf(rows);

  return (
    <Box sx={{ overflowX: 'auto', border: `1px solid ${color.hairline}`, borderRadius: '6px' }}>
      <Table size="small" sx={{ minWidth: Math.min(columns.length * 150, 900) }}>
        <TableHead>
          <TableRow>
            {columns.map((key) => (
              <TableCell key={key} sx={{
                fontFamily: font.mono, fontSize: 10, letterSpacing: '0.06em',
                textTransform: 'uppercase', color: color.muted,
                borderBottom: `1px solid ${color.hairline}`, whiteSpace: 'nowrap',
              }}>
                {key}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={index}>
              {columns.map((key) => (
                <TableCell key={key} sx={{
                  verticalAlign: 'top', borderBottom: `1px solid ${color.hairline}`,
                  fontSize: 13, maxWidth: 360,
                }}>
                  <StructuredValue value={row[key]} depth={depth + 1} />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function KeyValueRows({ value, depth }: { value: Record<string, unknown>; depth: number }) {
  const entries = Object.entries(value);
  if (entries.length === 0) return <Absent label="Nessun campo" />;

  return (
    <Box sx={{ display: 'grid', gap: 0.25 }}>
      {entries.map(([key, child]) => (
        <Box key={key} sx={{
          display: 'flex', gap: 1.5, alignItems: 'baseline',
          py: 0.4, borderBottom: `1px solid ${color.hairline}`,
        }}>
          <Typography sx={{
            fontFamily: font.mono, fontSize: 11, color: color.muted,
            minWidth: 132, flexShrink: 0, wordBreak: 'break-word',
          }}>
            {key}
          </Typography>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <StructuredValue value={child} depth={depth + 1} />
          </Box>
        </Box>
      ))}
    </Box>
  );
}

/** Ultima risorsa oltre `MAX_DEPTH`. Resta leggibile e non è mai una coercizione. */
function JsonInspector({ value }: { value: unknown }) {
  return (
    <Box component="pre" tabIndex={0} sx={{
      fontFamily: font.mono, fontSize: 11, lineHeight: 1.5, m: 0, p: 1,
      backgroundColor: '#fafafa', border: `1px solid ${color.hairline}`,
      borderRadius: '6px', overflowX: 'auto', maxHeight: 260, whiteSpace: 'pre-wrap',
    }}>
      {JSON.stringify(value, null, 2)}
    </Box>
  );
}

export interface StructuredValueProps {
  value: unknown;
  depth?: number;
}

export default function StructuredValue({ value, depth = 0 }: StructuredValueProps) {
  if (value === null || value === undefined) return <Absent label="Non disponibile" />;
  if (isPrimitive(value)) return <Scalar value={value} />;

  if (Array.isArray(value)) {
    if (value.length === 0) return <Absent label="Nessun elemento" />;

    if (value.every(isPrimitive)) {
      return (
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
          {value.map((item, index) => <Scalar key={index} value={item} />)}
        </Stack>
      );
    }

    if (depth >= MAX_DEPTH) return <JsonInspector value={value} />;

    if (value.every(isPlainObject)) {
      return <ArrayTable rows={value as Array<Record<string, unknown>>} depth={depth} />;
    }

    // Array eterogeneo: ogni elemento con la propria resa, numerato per non
    // perdere la posizione.
    return (
      <Stack spacing={0.75}>
        {value.map((item, index) => (
          <Box key={index} sx={{ display: 'flex', gap: 1, alignItems: 'baseline' }}>
            <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
              {index}
            </Typography>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <StructuredValue value={item} depth={depth + 1} />
            </Box>
          </Box>
        ))}
      </Stack>
    );
  }

  if (isPlainObject(value)) {
    if (depth >= MAX_DEPTH) return <JsonInspector value={value} />;
    return <KeyValueRows value={value} depth={depth} />;
  }

  // Nessun altro tipo raggiunge una preview del backend (che è JSON), ma un
  // fallback che non sia una coercizione va comunque previsto.
  return <JsonInspector value={value} />;
}

export { JsonInspector };
