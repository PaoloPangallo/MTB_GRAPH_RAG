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
