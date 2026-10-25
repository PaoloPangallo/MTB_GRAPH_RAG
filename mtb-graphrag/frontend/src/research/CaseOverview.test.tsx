import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import CaseOverview from './CaseOverview';

describe('CaseOverview', () => {
  it('does not invent zero counts for a historical dossier without canonical arrays', () => {
    render(<CaseOverview dossier={{}} />);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });
  it('links canonical counts to each source and keeps limits and narrative accessible', () => {
    render(<CaseOverview dossier={{ paper_evidence: [{ candidate_id: 'p1' }], clinical_trials: [], kg_only_relations: [{ candidate_id: 'k1' }, { candidate_id: 'k2' }] }} />);
    expect(screen.getByRole('link', { name: 'Pubblicazioni 1' })).toHaveAttribute('href', '#dossier-paper');
    expect(screen.getByRole('link', { name: 'Studi clinici 0' })).toHaveAttribute('href', '#dossier-trial');
    expect(screen.getByRole('link', { name: 'Knowledge Graph 2' })).toHaveAttribute('href', '#dossier-kg');
    expect(screen.getByRole('link', { name: 'Limiti del dossier' })).toHaveAttribute('href', '#dossier-limits');
    expect(screen.getByRole('link', { name: 'Sintesi narrativa' })).toHaveAttribute('href', '#case-narrative');
    expect(screen.getByText(/non misure di efficacia clinica/)).toBeVisible();
  });
});
