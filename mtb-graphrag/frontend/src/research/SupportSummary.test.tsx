import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SupportSummary from './SupportSummary';

describe('SupportSummary', () => {
  it('keeps missing classifications separate from unverifiable evidence', () => {
    render(<SupportSummary dossier={{ paper_evidence: [
      { candidate_id: 'a', support_level: 'FULL_SUPPORT' },
      { candidate_id: 'b', support_level: 'UNVERIFIABLE' },
      { candidate_id: 'c' },
    ] }} />);
    expect(screen.getByText(/3 relazioni cercate/)).toHaveTextContent('0 record conservati');
    expect(screen.queryByText(/supporto pieno/)).not.toBeInTheDocument();
  });
  it('does not manufacture paper support for a KG-only case', () => {
    const { container } = render(<SupportSummary dossier={{ paper_evidence: [], kg_only_relations: [{ candidate_id: 'kg' }] }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
