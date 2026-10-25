import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import EntityResolutionTrace from './EntityResolutionTrace';

describe('entity resolution trace', () => {
  it('separates identity from support and shows limitations', () => {
    render(<EntityResolutionTrace value={{ registry_version: 'terminology/1.0', diseases: [
      { raw_value: 'metastatic CRC', status: 'RESOLVED', concept_ids: ['DOID:9256'], residual_context: 'metastatic' },
      { raw_value: 'shared', status: 'AMBIGUOUS', concept_ids: ['DOID:1', 'DOID:2'] },
      { raw_value: 'unknown', status: 'UNMAPPED', concept_ids: [] },
    ] }} />);
    expect(screen.getByText('metastatic CRC')).toBeInTheDocument();
    expect(screen.getByText('DOID:9256')).toBeInTheDocument();
    expect(screen.getByText(/Identità ambigua/)).toBeInTheDocument();
    expect(screen.getByText(/Concetto non risolto/)).toBeInTheDocument();
    expect(screen.getByText(/Autenticazione e corrispondenza documentale/)).toBeInTheDocument();
  });
});
