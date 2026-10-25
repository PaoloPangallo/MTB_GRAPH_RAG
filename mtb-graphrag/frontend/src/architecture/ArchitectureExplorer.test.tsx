import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ArchitectureExplorer from './ArchitectureExplorer';
import { demoScenarios } from './model';

function renderExplorer() {
  return render(<MemoryRouter initialEntries={['/architecture?mode=demo']}><ArchitectureExplorer /></MemoryRouter>);
}

function advance(count: number) {
  for (let step = 0; step < count; step += 1) fireEvent.click(screen.getByRole('button', { name: 'Passaggio successivo' }));
}

afterEach(() => vi.useRealTimers());

describe('Architecture Explorer: comprensione e navigazione', () => {
  it('opens on a readable scenario and does not reveal its final dossier early', () => {
    renderExplorer();
    expect(screen.getByRole('heading', { name: 'Come GCA4 costruisce un dossier' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ingresso del caso' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Risultato del dossier' })).not.toBeInTheDocument();
  });

  it('advances, goes backward and resets to the beginning', () => {
    renderExplorer();
    advance(1);
    expect(screen.getByRole('heading', { name: 'Estrazione strutturata' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Passaggio precedente' }));
    expect(screen.getByRole('heading', { name: 'Ingresso del caso' })).toBeInTheDocument();
    advance(3);
    fireEvent.click(screen.getByRole('button', { name: 'Ricomincia' }));
    expect(screen.getByRole('heading', { name: 'Ingresso del caso' })).toBeInTheDocument();
  });

  it('makes component inspection work even after the simulation has started', () => {
    renderExplorer();
    advance(1);
    fireEvent.click(screen.getByRole('button', { name: 'Mappa completa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ispeziona Reader 4.9' }));
    expect(screen.getByRole('heading', { name: 'Reader 4.9' })).toBeInTheDocument();
    expect(screen.getByText(/Input: contesto autorizzato/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Torna al passaggio corrente' }));
    expect(screen.getByRole('heading', { name: 'Estrazione strutturata' })).toBeInTheDocument();
  });

  it('plays at a readable pace and really stops when paused', () => {
    vi.useFakeTimers();
    renderExplorer();
    fireEvent.click(screen.getByRole('button', { name: 'Riproduci' }));
    act(() => vi.advanceTimersByTime(2800));
    expect(screen.getByRole('heading', { name: 'Estrazione strutturata' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Pausa' }));
    act(() => vi.advanceTimersByTime(6000));
    expect(screen.getByRole('heading', { name: 'Estrazione strutturata' })).toBeInTheDocument();
  });

  it('makes the gate branch conditions visible in component inspection', () => {
    renderExplorer();
    fireEvent.click(screen.getByRole('button', { name: 'Mappa completa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Ispeziona Gate strutturale' }));
    expect(screen.getByText('PASS · EVIDENCE_DRUG')).toBeInTheDocument();
    expect(screen.getByText('MISMATCH / UNRESOLVED')).toBeInTheDocument();
  });

  it('shows an authentic citation blocked without a semantic call', () => {
    renderExplorer();
    fireEvent.change(screen.getByRole('combobox', { name: 'Scenario' }), { target: { value: 'structural-rejection' } });
    advance(9);
    expect(screen.getByRole('heading', { name: 'Mismatch dimostrato' })).toBeInTheDocument();
    expect(screen.getByText(/semantic verifier NON eseguito/)).toBeInTheDocument();
  });

  it('reveals a partial, failed-accounting dossier only at the final output', () => {
    renderExplorer();
    fireEvent.change(screen.getByRole('combobox', { name: 'Scenario' }), { target: { value: 'fallback-partial' } });
    expect(screen.queryByRole('heading', { name: 'Risultato del dossier' })).not.toBeInTheDocument();
    const count = demoScenarios.find((scenario) => scenario.id === 'fallback-partial')!.events.length;
    advance(count - 1);
    expect(screen.getByRole('heading', { name: 'Risultato del dossier' })).toBeInTheDocument();
    expect(screen.getByText('PARTIAL · ACCOUNTING FAIL')).toBeInTheDocument();
    expect(screen.getByText('PMID DEMO-004 · SourceUnit DEMO-SU-01')).toBeInTheDocument();
  });

  it('shows the KG_ONLY route without misleading Reader or documentary stages', () => {
    renderExplorer();
    fireEvent.change(screen.getByRole('combobox', { name: 'Scenario' }), { target: { value: 'families-kg' } });
    expect(screen.queryByRole('button', { name: /Vai al passaggio.*Reader/ })).not.toBeInTheDocument();
    advance(4);
    expect(screen.getByRole('heading', { name: 'Ramo KG_ONLY' })).toBeInTheDocument();
    expect(screen.getByText(/Reader non eseguito/)).toBeInTheDocument();
  });
});
