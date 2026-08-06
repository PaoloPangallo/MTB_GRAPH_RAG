/**
 * La modalità si sceglie. Prima veniva dedotta dal testo, e il criterio —
 * "coincide con un caso dimostrativo, quindi replay" — rendeva impossibile
 * eseguire dal vivo proprio i casi per cui il confronto conta di più.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CaseInputPanel from './CaseInputPanel';
import type { DemoCase } from './types';

const CASES: DemoCase[] = [
  {
    case_id: 'CASE-1-therapy-evaluation-strong-match',
    clinical_text: 'Paziente con carcinoma colorettale metastatico e mutazione KRAS G12D.',
    expected_query_intent: 'THERAPY_EVALUATION',
    expected_result: 'match forte',
    frozen_artifacts_available: true,
  },
];

function renderPanel(props: Partial<React.ComponentProps<typeof CaseInputPanel>> = {}) {
  const onRun = vi.fn();
  render(<CaseInputPanel cases={CASES} busy={false} onRun={onRun} {...props} />);
  return onRun;
}

function fillWithDemoText() {
  fireEvent.change(screen.getByLabelText('Testo clinico in linguaggio libero'), {
    target: { value: CASES[0].clinical_text },
  });
}

describe('CaseInputPanel', () => {
  it('parte in LIVE', () => {
    renderPanel();
    expect(screen.getByTestId('mode-live')).toHaveAttribute('aria-pressed', 'true');
  });

  it('esegue LIVE anche un caso che ha artefatti registrati', () => {
    const onRun = renderPanel();
    fillWithDemoText();
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({
      demo_case_key: CASES[0].case_id,
      execution_mode: 'LIVE',
    }));
  });

  it('esegue REPLAY solo se richiesto esplicitamente', () => {
    const onRun = renderPanel();
    fillWithDemoText();
    fireEvent.click(screen.getByTestId('mode-replay'));
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ execution_mode: 'REPLAY' }));
  });

  it('un testo libero dichiara comunque la propria modalità', () => {
    const onRun = renderPanel();
    fireEvent.change(screen.getByLabelText('Testo clinico in linguaggio libero'), {
      target: { value: 'Paziente con adenocarcinoma polmonare EGFR L858R.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({
      execution_mode: 'LIVE',
      clinical_text: 'Paziente con adenocarcinoma polmonare EGFR L858R.',
    }));
  });

  it('avvisa che senza cache una run LIVE fallisce, senza ripiegare sul replay', () => {
    renderPanel({ liveAvailable: false });
    fillWithDemoText();

    expect(screen.getByText(/DOCUMENT_CACHE_UNAVAILABLE/)).toBeInTheDocument();
    expect(screen.getByText(/Non viene sostituita da una run/)).toBeInTheDocument();
  });

  it('non avvia una run LIVE quando la cache manca', () => {
    const onRun = renderPanel({ liveAvailable: false });
    fillWithDemoText();
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).not.toHaveBeenCalled();
  });

  it('non avvia una run REPLAY se non c’è nulla da rigiocare', () => {
    const onRun = renderPanel();
    fireEvent.change(screen.getByLabelText('Testo clinico in linguaggio libero'), {
      target: { value: 'Testo mai visto prima.' },
    });
    fireEvent.click(screen.getByTestId('mode-replay'));
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).not.toHaveBeenCalled();
    expect(screen.getByText(/non avrebbe nulla da rigiocare/)).toBeInTheDocument();
  });

  it('dichiara che un replay non è una run eseguita ora', () => {
    renderPanel();
    fillWithDemoText();
    fireEvent.click(screen.getByTestId('mode-replay'));

    expect(screen.getByText(/non vengono prodotte ora/)).toBeInTheDocument();
    expect(screen.getByText(/non potrà essere\s+presentata come live/)).toBeInTheDocument();
  });
});
