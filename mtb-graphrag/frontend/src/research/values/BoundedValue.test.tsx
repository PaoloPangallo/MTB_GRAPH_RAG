import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import BoundedValue from './BoundedValue';

describe('ispezione di artefatti grandi', () => {
  it('rende una sola pagina e permette di consultare anche gli ultimi elementi', () => {
    render(<BoundedValue value={Array.from({ length: 45 }, (_, index) => `record-${index}`)} />);
    expect(screen.getByText('record-0')).toBeInTheDocument();
    expect(screen.queryByText('record-44')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Pagina successiva' }));
    fireEvent.click(screen.getByRole('button', { name: 'Pagina successiva' }));
    expect(screen.getByText('record-44')).toBeInTheDocument();
    expect(screen.queryByText('record-0')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Pagina precedente' }));
    expect(screen.getByText('record-20')).toBeInTheDocument();
  });

  it('monta ogni ramo annidato solo su apertura e lo smonta su chiusura', () => {
    render(<BoundedValue value={{ branch: { value: 'DEEP_VALUE_ONLY_ON_OPEN' } }} />);
    expect(screen.queryByText('DEEP_VALUE_ONLY_ON_OPEN')).not.toBeInTheDocument();
    const details = screen.getByText(/branch.*1 campo/).closest('details')!;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    expect(screen.getByText('DEEP_VALUE_ONLY_ON_OPEN')).toBeInTheDocument();
    details.open = false;
    fireEvent(details, new Event('toggle'));
    expect(screen.queryByText('DEEP_VALUE_ONLY_ON_OPEN')).not.toBeInTheDocument();
  });
});
