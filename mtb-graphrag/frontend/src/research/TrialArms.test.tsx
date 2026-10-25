import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TrialStudies from './TrialStudies';
import CaseSummaryView from './CaseSummaryView';
import ObservedFields from './ObservedFields';

describe('attribuzione dei bracci e limiti molecolari', () => {
  it('distingue alternative molecolari da combinazione terapeutica', () => {
    render(<ObservedFields observed={{ molecular_composition: 'ALTERNATIVES', intervention_composition: 'COMBINATION' }} />);
    expect(screen.getByText('Composizione molecolare')).toBeInTheDocument();
    expect(screen.getByText('Varianti alternative o coorti distinte')).toBeInTheDocument();
    expect(screen.getByText('Combinazione')).toBeInTheDocument();
  });
  it('mantiene popolazione e farmaci dentro ciascun braccio', () => {
    render(<TrialStudies entries={[{ candidate_id: 'T', nct_id: 'NCT02465060',
      arm_groups: [
        { label: 'NRAS cohort', description: 'NRAS mutation-positive melanoma', interventionNames: ['Drug: Binimetinib'] },
        { label: 'Other cohort', description: 'Different molecular cohort', interventionNames: ['Drug: Trametinib'] },
      ] }]} />);
    const nras = screen.getByRole('heading', { name: 'NRAS cohort' }).closest('article')!;
    expect(within(nras).getByText('NRAS mutation-positive melanoma')).toBeInTheDocument();
    expect(within(nras).getByText(/Drug: Binimetinib/)).toBeInTheDocument();
    expect(within(nras).queryByText(/Trametinib/)).not.toBeInTheDocument();
  });
  it('non attribuisce gli interventi dello studio ai bracci mancanti', () => {
    render(<TrialStudies entries={[{ candidate_id: 'T', nct_id: 'NCT02465060', interventions: ['Trametinib'] }]} />);
    expect(screen.getByText(/Bracci non disponibili/)).toBeInTheDocument();
    expect(screen.getByText(/Interventi dello studio complessivo/)).toHaveTextContent('Trametinib');
  });
  it('tiene l’elenco globale nei dettagli quando sono disponibili i singoli bracci', () => {
    render(<TrialStudies entries={[{ candidate_id: 'T', nct_id: 'NCT02465060', interventions: ['Global-only drug'],
      arm_groups: [{ label: 'NRAS cohort', interventionNames: ['Binimetinib'] }] }]} />);
    const details = screen.getByText('Condizioni e interventi dello studio complessivo').closest('details')!;
    expect(details).not.toHaveAttribute('open');
    expect(within(details).getByText(/Global-only drug/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'NRAS cohort' })).toBeVisible();
  });
  it('conserva dati discordanti per lo stesso NCT senza fondere i bracci', () => {
    render(<TrialStudies entries={[
      { candidate_id: 'T1', nct_id: 'NCT02465060', title: 'Study', arm_groups: [{ label: 'Arm A', interventionNames: ['Drug X'] }] },
      { candidate_id: 'T2', nct_id: 'NCT02465060', title: 'Study', arm_groups: [{ label: 'Arm B', interventionNames: ['Drug Y'] }] },
    ]} />);
    expect(screen.getByText(/Dati di registro discordanti/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Arm A' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Arm B' })).toBeInTheDocument();
  });
  it('mostra il profilo di fusione irrisolto senza inventare identita', () => {
    render(<CaseSummaryView value={{ gene: 'ROS1', variant: 'fusione CD74-ROS1', molecular_resolution: [
      { fusion_partners: ['CD74', 'ROS1'], fusion_status: 'UNMAPPED', fusion_concept_ids: [] },
    ] }} />);
    expect(screen.getByText(/Profilo di fusione non risolto/)).toHaveTextContent('CD74');
    expect(screen.getByText(/Profilo di fusione non risolto/)).toHaveTextContent('ROS1');
  });
  it('rende leggibili entrambi i titoli discordanti', () => {
    render(<TrialStudies entries={[
      { candidate_id: 'T1', nct_id: 'NCT02465060', title: 'Original registry title' },
      { candidate_id: 'T2', nct_id: 'NCT02465060', title: 'Updated registry title' },
    ]} />);
    expect(screen.getByRole('heading', { name: 'Dati registrati 1: Original registry title' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Dati registrati 2: Updated registry title' })).toBeInTheDocument();
  });
  it('permette di trovare un braccio oltre la prima pagina senza inferire eleggibilita', () => {
    const arms = Array.from({ length: 8 }, (_, index) => ({ label: `Arm ${index}`, description: `Cohort ${index}`, interventionNames: [`Drug ${index}`] }));
    render(<TrialStudies entries={[{ candidate_id: 'T', nct_id: 'NCT02465060', arm_groups: arms }]} />);
    expect(screen.queryByRole('heading', { name: 'Arm 7' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Cerca nei bracci dello studio'), { target: { value: 'Cohort 7' } });
    expect(screen.getByRole('heading', { name: 'Arm 7' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Arm 0' })).not.toBeInTheDocument();
    expect(screen.getByText(/Eleggibilità del paziente non valutata/)).toBeInTheDocument();
  });
});
