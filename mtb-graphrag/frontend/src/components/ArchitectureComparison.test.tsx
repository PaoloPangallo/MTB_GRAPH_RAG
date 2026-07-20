import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ArchitecturePanel } from './ArchitectureComparison';
import type { ArchitectureRun } from '../types';

function buildRun(overrides: Partial<ArchitectureRun> = {}): ArchitectureRun {
  return {
    architecture_id: 'deterministic',
    title: 'Traversal deterministico',
    subtitle: 'test fixture',
    llm_roles: [],
    trace: [],
    evidence: [],
    report: 'Testo grezzo di prova con formulazioni non verificate.',
    dossier: {
      case_summary: [],
      missing_data: [],
      evidence: [],
      resistance_findings: [],
      trial_findings: [],
      mtb_questions: [],
    },
    claim_checks: [],
    metrics: {
      elapsed_ms: 10,
      tool_calls: 1,
      evidence_count: 0,
      verified_claims: 0,
      blocked_claims: 0,
    },
    limitations: [],
    ...overrides,
  };
}

describe('ArchitecturePanel — pannello output grezzo del traversal', () => {
  it('è collassato di default e marcato come non verificato', () => {
    render(<ArchitecturePanel run={buildRun()} />);
    const trigger = screen.getByRole('button', { name: /Output LLM non verificato/i });
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('mostra un avviso sulle formulazioni non supportate quando espanso', async () => {
    render(<ArchitecturePanel run={buildRun()} />);
    expect(
      screen.getByText(/può contenere formulazioni non supportate/i),
    ).toBeInTheDocument();
  });

  it('non applica lo stesso collasso al report agentico, che resta etichettato come solo-supporto', () => {
    render(<ArchitecturePanel run={buildRun({ architecture_id: 'agentic', title: 'Architettura agentica verificabile' })} />);
    expect(screen.queryByText('Output LLM non verificato — solo analisi sperimentale')).not.toBeInTheDocument();
    expect(screen.getByText(/Report verificato \(testo\)/)).toBeInTheDocument();
  });
});

describe('ArchitecturePanel — banner safe_fallback', () => {
  it('dichiara che il fallback non equivale a pianificazione dinamica riuscita', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          architecture_id: 'agentic',
          planning_mode: 'safe_fallback',
          fallback_reason: 'timeout',
        })}
      />,
    );
    expect(
      screen.getByText('Il planner LLM non ha completato un piano valido; è stato eseguito il piano sicuro predefinito.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Causa: timeout/)).toBeInTheDocument();
  });

  it('non mostra il banner quando la pianificazione dinamica è riuscita', () => {
    render(<ArchitecturePanel run={buildRun({ architecture_id: 'agentic', planning_mode: 'llm_dynamic' })} />);
    expect(
      screen.queryByText('Il planner LLM non ha completato un piano valido; è stato eseguito il piano sicuro predefinito.'),
    ).not.toBeInTheDocument();
  });
});
