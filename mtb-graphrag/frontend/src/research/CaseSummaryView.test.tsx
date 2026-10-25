import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import CaseSummaryView from './CaseSummaryView';
function toggle(details: HTMLDetailsElement, open: boolean) { details.open = open; fireEvent(details, new Event('toggle')); }
describe('CaseSummaryView', () => {
  it('etichetta i campi noti e conserva i valori', () => {
    render(<CaseSummaryView value={{ disease: 'colorectal cancer', variant: null, intent: 'THERAPY_SEARCH' }} />);
    expect(screen.getByText('Patologia')).toBeInTheDocument();
    expect(screen.getByText('Alterazione')).toBeInTheDocument();
    expect(screen.getByText('colorectal cancer')).toBeInTheDocument();
    expect(screen.getByText('THERAPY_SEARCH')).toBeInTheDocument();
    expect(screen.queryByText('disease')).not.toBeInTheDocument();
  });
  it('preserva campi sconosciuti e annidati nei dettagli differiti', () => {
    render(<CaseSummaryView value={{ disease: { original: 'NESTED_VALUE' }, unknown_field: 'UNKNOWN_VALUE' }} />);
    expect(screen.queryByText('UNKNOWN_VALUE')).not.toBeInTheDocument();
    const details = screen.getByText('Campi canonici e dettagli tecnici del caso').closest('details')!;
    toggle(details, true);
    expect(screen.getByText('UNKNOWN_VALUE')).toBeInTheDocument();
    toggle(screen.getByText(/disease.*1 campo/).closest('details')!, true);
    expect(screen.getByText('NESTED_VALUE')).toBeInTheDocument();
    toggle(details, false);
    expect(screen.queryByText('UNKNOWN_VALUE')).not.toBeInTheDocument();
    expect(screen.queryByText('NESTED_VALUE')).not.toBeInTheDocument();
  });
});
