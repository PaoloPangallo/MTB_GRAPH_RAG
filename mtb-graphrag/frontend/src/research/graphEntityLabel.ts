export interface GraphEntity {
  id?: string;
  label?: string;
  type?: string;
}

/** Una label Evidence è uno statement curato del grafo, non una quote validata. */
export function graphEntityLabel(entity?: GraphEntity | null): string | undefined {
  if (entity?.type === 'Evidence') return entity.id ?? 'Statement del grafo';
  return entity?.label ?? entity?.id;
}
