/**
 * Non c'è una modalità da scegliere.
 *
 * Il pannello ha avuto due versioni sbagliate per ragioni opposte: prima la
 * modalità veniva dedotta dal testo — «coincide con un caso dimostrativo, quindi
 * replay» — poi diventò un interruttore esplicito. La deduzione era un fallback
 * silenzioso; l'interruttore chiedeva al clinico di sapere cosa fosse un
 * artefatto congelato. Questi test fissano la terza forma: il clinico inserisce
 * il caso, e il sistema esegue l'unico percorso che ha.
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
  },
];

function renderPanel(props: Partial<React.ComponentProps<typeof CaseInputPanel>> = {}) {
  const onRun = vi.fn();
  render(<CaseInputPanel cases={CASES} observedCases={[]} busy={false} onRun={onRun} {...props} />);
  return onRun;
}

function fillWithDemoText() {
  fireEvent.change(screen.getByLabelText('Testo clinico in linguaggio libero'), {
    target: { value: CASES[0].clinical_text },
  });
}

describe('CaseInputPanel', () => {
  it('usa un esempio eseguito e mostra gli esiti osservati senza trasformarli in risultati della nuova run', () => {
    const text = 'Synthetic research case. Molecular profiling reports MAP2K1.';
    const onRun = renderPanel({ observedCases: [{ case_id: 'DEMO-KG', title: 'MAP2K1 — relazioni del grafo', clinical_text: text, group: 'KG', counts: { PAPER: 0, TRIAL: 0, KG: 84 }, status: 'COMPLETED', run_id: 'recorded-run', observed_at: '2026-10-07', presentation_mode: 'VERIFIED_NARRATIVE' }] });
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Scegli un caso di esempio' }));
    fireEvent.click(screen.getByRole('option', { name: 'MAP2K1 — relazioni del grafo' }));
    expect(screen.getByText(/Ultima esecuzione osservata/)).toBeInTheDocument();
    expect(screen.getByText(/84 relazioni KG/)).toBeInTheDocument();
    expect(onRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));
    expect(onRun.mock.calls[0][0]).toMatchObject({ clinical_text: text });
    expect(onRun.mock.calls[0][0]).not.toHaveProperty('demo_case_key');
    expect(onRun.mock.calls[0][0]).not.toHaveProperty('counts');
  });
  it('sceglie un esempio dal menu con nome significativo e compila il testo senza avviare', () => {
    const onRun = renderPanel();
    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Scegli un caso di esempio' }));
    fireEvent.click(screen.getByRole('option', { name: 'Colon-retto · KRAS G12D — valutazione di panitumumab' }));
    expect(screen.getByLabelText('Testo clinico in linguaggio libero')).toHaveValue(CASES[0].clinical_text);
    expect(onRun).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));
    expect(onRun).toHaveBeenCalledWith({ demo_case_key: CASES[0].case_id });
  });
  it('mostra i tre esempi di ramo oltre ai casi dimostrativi caricati', () => {
    renderPanel();

    expect(screen.getByText('PAPER')).toBeInTheDocument();
    expect(screen.getByText('TRIAL')).toBeInTheDocument();
    expect(screen.getByText('KG ONLY')).toBeInTheDocument();
  });

  it('non offre alcun selettore di modalità', () => {
    renderPanel();

    expect(screen.queryByTestId('mode-live')).not.toBeInTheDocument();
    expect(screen.queryByTestId('mode-replay')).not.toBeInTheDocument();
    expect(screen.queryByText(/REPLAY/)).not.toBeInTheDocument();
  });

  it('avvia un caso dimostrativo senza dichiarare nulla oltre al caso', () => {
    const onRun = renderPanel();
    fillWithDemoText();
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).toHaveBeenCalledWith({ demo_case_key: CASES[0].case_id });
  });

  it('avvia un testo libero con un identificativo proprio', () => {
    const onRun = renderPanel();
    fireEvent.change(screen.getByLabelText('Testo clinico in linguaggio libero'), {
      target: { value: 'Paziente con adenocarcinoma polmonare EGFR L858R.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    const request = onRun.mock.calls[0][0];
    expect(request.clinical_text).toBe('Paziente con adenocarcinoma polmonare EGFR L858R.');
    expect(request.case_id).toMatch(/^FREETEXT-/);
    expect(request).not.toHaveProperty('execution_mode');
  });

  it('senza cache distingue i percorsi documentali dal ramo KG_ONLY', () => {
    renderPanel({ documentCacheAvailable: false });
    fillWithDemoText();

    expect(screen.getByTestId('document-cache-unavailable')).toBeInTheDocument();
    expect(screen.getByText(/KG_ONLY resta eseguibile/)).toBeInTheDocument();
  });

  it('senza cache lascia al backend il routing del caso', () => {
    const onRun = renderPanel({ documentCacheAvailable: false });
    fillWithDemoText();
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).toHaveBeenCalledWith({ demo_case_key: CASES[0].case_id });
  });

  it('un testo mai visto è eseguibile quanto un caso dimostrativo', () => {
    // Prima non lo era: senza artefatti congelati corrispondenti, la modalità
    // REPLAY non aveva nulla da rigiocare e il pannello rifiutava di partire.
    const onRun = renderPanel();
    fireEvent.change(screen.getByLabelText('Testo clinico in linguaggio libero'), {
      target: { value: 'Testo mai visto prima.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Esegui la pipeline/ }));

    expect(onRun).toHaveBeenCalledTimes(1);
  });
});
