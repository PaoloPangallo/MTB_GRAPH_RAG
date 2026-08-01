import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import V3RunForm from './V3RunForm';

describe('V3RunForm', () => {
  it('sends the explicit intervention and direction in the V3 payload', () => {
    const onSubmit = vi.fn();
    render(<V3RunForm disabled={false} onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('Gene'), {
      target: { value: 'EGFR' },
    });
    fireEvent.change(screen.getByLabelText('Alterazione'), {
      target: { value: 'L858R' },
    });
    fireEvent.change(screen.getByLabelText('Malattia'), {
      target: { value: 'Lung Adenocarcinoma' },
    });
    fireEvent.change(screen.getByLabelText('Interventi'), {
      target: { value: 'osimertinib' },
    });
    fireEvent.change(screen.getByLabelText('Direzione'), {
      target: { value: 'sensitivity' },
    });
    fireEvent.change(screen.getByLabelText('Limite risultati'), {
      target: { value: '20' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Esegui pipeline V3' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        gene: 'EGFR',
        alteration: 'L858R',
        disease: 'Lung Adenocarcinoma',
        interventions: ['osimertinib'],
        direction: 'sensitivity',
        policy_mode: 'strict_verified',
        result_limit: 20,
      }),
    );
  });

  it('does not expose OncoKB or a legacy report action', () => {
    render(<V3RunForm disabled={false} onSubmit={vi.fn()} />);

    expect(screen.queryByText(/OncoKB/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Genera Report GraphRAG/i)).not.toBeInTheDocument();
  });
});
