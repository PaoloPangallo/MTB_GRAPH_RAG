import { Box, Button, Stack, Typography } from '@mui/material';
import { useState } from 'react';
import StructuredValue from './StructuredValue';
import { color, font } from '../tokens';

const PAGE_SIZE = 20;

function isContainer(value: unknown): value is Record<string, unknown> | unknown[] {
  return value !== null && typeof value === 'object';
}

function Branch({ label, value }: { label: string; value: Record<string, unknown> | unknown[] }) {
  const [open, setOpen] = useState(false);
  const array = Array.isArray(value);
  const count = array ? value.length : Object.keys(value).length;
  const unit = array ? (count === 1 ? 'elemento' : 'elementi') : (count === 1 ? 'campo' : 'campi');
  return <Box component="details" onToggle={event => setOpen(event.currentTarget.open)} sx={{ py: 0.5 }}>
    <Box component="summary" sx={{ cursor: 'pointer', fontFamily: font.mono, fontSize: 12 }}>{label} · {count} {unit}</Box>
    {open && <Box sx={{ pl: 2, mt: 1 }}><BoundedValue value={value} /></Box>}
  </Box>;
}

/** Vista del JSON canonico: pagine di fratelli, rami costruiti soltanto su apertura.
 * Nessun campo viene eliminato o ricalcolato; evita di serializzare l'intero artefatto.
 */
export default function BoundedValue({ value }: { value: unknown }) {
  const [page, setPage] = useState(0);
  if (!isContainer(value)) return <StructuredValue value={value} />;
  const array = Array.isArray(value);
  const keys = array ? null : Object.keys(value);
  const count = array ? value.length : keys!.length;
  if (count === 0) return <StructuredValue value={value} />;
  const current = Math.min(page, Math.ceil(count / PAGE_SIZE) - 1);
  const start = current * PAGE_SIZE;
  const entries: [string, unknown][] = array
    ? value.slice(start, start + PAGE_SIZE).map((child, index) => [`[${start + index}]`, child])
    : keys!.slice(start, start + PAGE_SIZE).map(key => [key, (value as Record<string, unknown>)[key]]);
  return <Box>
    {entries.map(([label, child]) => isContainer(child)
      ? <Branch key={label} label={label} value={child} />
      : <Box key={label} sx={{ py: 0.5, borderBottom: `1px solid ${color.hairline}`, overflowWrap: 'anywhere' }}>
        <Typography component="span" sx={{ fontFamily: font.mono, color: color.muted, fontSize: 11, mr: 1 }}>{label}</Typography>
        <StructuredValue value={child} />
      </Box>)}
    {count > PAGE_SIZE && <Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: 'center' }}>
      <Button disabled={current === 0} onClick={() => setPage(current - 1)}>Pagina precedente</Button>
      <Typography variant="body2">{start + 1}–{Math.min(start + PAGE_SIZE, count)} di {count}</Typography>
      <Button disabled={start + PAGE_SIZE >= count} onClick={() => setPage(current + 1)}>Pagina successiva</Button>
    </Stack>}
  </Box>;
}
