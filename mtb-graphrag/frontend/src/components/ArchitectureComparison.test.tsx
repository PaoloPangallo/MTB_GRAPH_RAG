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

describe('ArchitecturePanel — etichette del contesto (paziente vs fonte recuperata)', () => {
  it('etichetta item.setting come contesto della fonte recuperata, non come dichiarazione del paziente', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          dossier: {
            case_summary: [
              { key: 'disease_stage', label: 'Stadio dichiarato dal paziente', value: 'IV', confirmed: true },
            ],
            missing_data: [],
            evidence: [
              {
                evidence_id: 'ev-1',
                claim: 'Claim di prova',
                therapy: 'Osimertinib',
                setting: 'NSCLC metastatico EGFR+',
                source_support_status: 'supported',
                source_support_reason: 'Supportata dalla fonte primaria.',
                applicability_status: 'compatible',
                applicability_reason: 'Compatibile con il contesto dichiarato.',
                requires_source_review: false,
                requires_clinical_review: false,
                dossier_section: 'supported_compatible',
              },
            ],
            resistance_findings: [],
            trial_findings: [],
            mtb_questions: [],
          },
        })}
      />,
    );

    expect(screen.getByText(/Tumore\/contesto del record recuperato: NSCLC metastatico EGFR\+/)).toBeInTheDocument();
    expect(screen.queryByText(/Contesto dichiarato dal paziente/)).not.toBeInTheDocument();
    expect(screen.getByText('Stadio dichiarato dal paziente')).toBeInTheDocument();
  });
});

describe('ArchitecturePanel — tempi delle chiamate agli strumenti', () => {
  it('non mostra la sezione quando tool_call_timings è assente', () => {
    render(<ArchitecturePanel run={buildRun()} />);
    expect(screen.queryByText('Tempi delle chiamate agli strumenti')).not.toBeInTheDocument();
  });

  it('mostra sequenza, nome tool, durata e stato quando disponibili', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          tool_call_timings: [
            { tool: 'interpret_variant', sequence: 1, elapsed_ms: 120, status: 'completed' },
            { tool: 'check_resistance', sequence: 2, elapsed_ms: 45, status: 'failed' },
          ],
        })}
      />,
    );
    expect(screen.getByText('Tempi delle chiamate agli strumenti')).toBeInTheDocument();
    expect(screen.getByText('interpret_variant')).toBeInTheDocument();
    expect(screen.getByText('120 ms')).toBeInTheDocument();
    expect(screen.getByText('check_resistance')).toBeInTheDocument();
    expect(screen.getByText('45 ms')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
  });
});

describe('ArchitecturePanel — diagnostica verificatore', () => {
  it('non mostra la sezione quando non ci sono batch del verificatore', () => {
    render(<ArchitecturePanel run={buildRun()} />);
    expect(screen.queryByText('Diagnostica verificatore')).not.toBeInTheDocument();
  });

  it('mostra batch, retry, recuperi e tempo del verificatore quando disponibili', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          metrics: {
            elapsed_ms: 10,
            tool_calls: 1,
            evidence_count: 14,
            verified_claims: 0,
            blocked_claims: 0,
            cache_hits: 5,
            cache_misses: 9,
            verifier_batches: 4,
            failed_batches: 1,
            retry_items: 3,
            recovered_items: 1,
            permanently_failed_items: 2,
            source_profile_elapsed_ms: 850,
            applicability_elapsed_ms: 12,
          },
        })}
      />,
    );
    expect(screen.getByText('Diagnostica verificatore')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('850 ms')).toBeInTheDocument();
  });

  it('mostra un warning quando più del 20% delle verifiche fallisce definitivamente', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          metrics: {
            elapsed_ms: 10,
            tool_calls: 1,
            evidence_count: 14,
            verified_claims: 0,
            blocked_claims: 0,
            verifier_batches: 4,
            failed_batches: 3,
            retry_items: 9,
            recovered_items: 0,
            permanently_failed_items: 9,
            source_profile_elapsed_ms: 5000,
          },
        })}
      />,
    );
    expect(screen.getByText(/Più del 20% delle verifiche è fallito definitivamente/)).toBeInTheDocument();
  });

  it('non mostra il warning quando i fallimenti definitivi restano sotto il 20%', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          metrics: {
            elapsed_ms: 10,
            tool_calls: 1,
            evidence_count: 14,
            verified_claims: 0,
            blocked_claims: 0,
            verifier_batches: 4,
            failed_batches: 1,
            retry_items: 1,
            recovered_items: 1,
            permanently_failed_items: 0,
            source_profile_elapsed_ms: 500,
          },
        })}
      />,
    );
    expect(screen.queryByText(/Più del 20% delle verifiche è fallito definitivamente/)).not.toBeInTheDocument();
  });
});

describe('ArchitecturePanel — campi del dossier clinico sempre etichettati', () => {
  it('mostra il valore dichiarato accanto alla propria etichetta', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          dossier: {
            case_summary: [{ key: 'tumor_type', label: 'Tumore', value: 'NSCLC', confirmed: true }],
            missing_data: [],
            evidence: [],
            resistance_findings: [],
            trial_findings: [],
            mtb_questions: [],
          },
        })}
      />,
    );
    expect(screen.getByText('Tumore')).toBeInTheDocument();
    expect(screen.getByText('NSCLC')).toBeInTheDocument();
  });

  it('non mostra mai "Da completare" senza un\'etichetta accanto, anche se il campo non è dichiarato', () => {
    render(
      <ArchitecturePanel
        run={buildRun({
          dossier: {
            case_summary: [{ key: 'disease_stage', label: 'Stadio', value: null, confirmed: false }],
            missing_data: ['Stadio'],
            evidence: [],
            resistance_findings: [],
            trial_findings: [],
            mtb_questions: [],
          },
        })}
      />,
    );
    expect(screen.getByText('Stadio')).toBeInTheDocument();
    expect(screen.getByText('Da completare')).toBeInTheDocument();
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
