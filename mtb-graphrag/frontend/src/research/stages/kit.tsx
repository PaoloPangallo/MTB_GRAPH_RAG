/**
 * Elementi condivisi dalle viste di stage.
 *
 * Esistono per una ragione sola: le viste specializzate devono poter dire
 * *chi ha prodotto un valore* e *quanto vale come prova* senza reinventare ogni
 * volta l'etichetta. Un badge scritto a mano in dieci punti diverge, e la
 * divergenza qui significa che due stage con la stessa garanzia la presentano
 * in modo diverso.
 */

import type { ReactNode } from 'react';
import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { color, font, radius } from '../tokens';

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <Typography sx={{
      fontFamily: font.mono, fontSize: 10, letterSpacing: '0.08em',
      textTransform: 'uppercase', color: color.muted, mb: 1,
    }}>
      {children}
    </Typography>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return (
    <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate, mb: 1.5 }}>
      {children}
    </Typography>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.muted, fontStyle: 'italic' }}>
      {children}
    </Typography>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box sx={{
      display: 'flex', gap: 2, py: 0.75, borderBottom: `1px solid ${color.hairline}`,
      alignItems: 'baseline',
    }}>
      <Typography sx={{
        fontFamily: font.body, fontSize: 12, color: color.slate,
        width: 160, flexShrink: 0,
      }}>
        {label}
      </Typography>
      <Box sx={{ minWidth: 0, flex: 1 }}>{children}</Box>
    </Box>
  );
}

export function Card({ children, tone }: { children: ReactNode; tone?: 'plain' | 'archive' }) {
  return (
    <Box sx={{
      border: `1px solid ${color.borderLight}`, borderRadius: `${radius.sm}px`,
      p: 2, mb: 1.5,
      backgroundColor: tone === 'archive' ? color.stone : 'transparent',
    }}>
      {children}
    </Box>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return (
    <Typography component="span" sx={{
      fontFamily: font.mono, fontSize: 12, color: color.body, wordBreak: 'break-all',
    }}>
      {children}
    </Typography>
  );
}

/** Badge neutro per un valore di enumerazione. */
export function Badge({ label, tone = 'neutral', title }: {
  label: string;
  tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'llm';
  title?: string;
}) {
  const tones = {
    neutral: { bg: color.stone, fg: color.body },
    good: { bg: '#edfce9', fg: color.deepGreen },
    warn: { bg: '#fff3ee', fg: '#8a4b2f' },
    bad: { bg: '#fdf0f0', fg: color.error },
    llm: { bg: color.coralSoft, fg: '#8a3a22' },
  }[tone];

  const chip = (
    <Chip label={label} size="small" sx={{
      height: 20, fontFamily: font.mono, fontSize: 10, letterSpacing: '0.04em',
      backgroundColor: tones.bg, color: tones.fg, borderRadius: '4px',
    }} />
  );
  return title ? <Tooltip title={title}>{chip}</Tooltip> : chip;
}

/**
 * Avviso che accompagna ogni oggetto derivato dal grafo.
 *
 * Non è decorativo: una GraphCandidateAssertion mostrata senza questa riga si
 * legge come un'evidenza documentale, che è la confusione che l'intera
 * architettura esiste per impedire.
 */
export function GraphDerivedWarning() {
  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5, flexWrap: 'wrap' }}>
      <Badge label="GRAPH-DERIVED" tone="warn" />
      <Typography sx={{ fontFamily: font.body, fontSize: 12, color: '#8a4b2f' }}>
        Candidate proposta dal grafo — non è ancora evidenza documentale
      </Typography>
    </Stack>
  );
}

/** Marca gli stage che rigiocano artefatti congelati invece di eseguirli ora. */
export function ReplayBadge() {
  return (
    <Badge
      label="REPLAY"
      title="Artefatto congelato del pilot: risposta reale del modello registrata, non rieseguita ora."
    />
  );
}

export function ReasonCodeList({ codes }: { codes: unknown }) {
  const list = Array.isArray(codes) ? codes.filter((c) => typeof c === 'string') as string[] : [];
  if (list.length === 0) return <Empty>Nessun reason code</Empty>;

  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', rowGap: 0.5 }}>
      {list.map((code) => <Badge key={code} label={code} />)}
    </Stack>
  );
}

/** Lettura difensiva di un preview di forma non garantita. */
export function rows(value: unknown, key: string): Array<Record<string, unknown>> {
  const raw = (value as Record<string, unknown> | null)?.[key];
  return Array.isArray(raw) ? raw.filter((r): r is Record<string, unknown> => typeof r === 'object' && r !== null) : [];
}

export function text(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

export function num(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}
