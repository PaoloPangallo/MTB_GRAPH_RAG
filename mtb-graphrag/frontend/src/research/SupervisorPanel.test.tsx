import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SupervisorPanel from './SupervisorPanel';
import type { PipelineEvent, RunMetrics } from './types';

const METRICS: RunMetrics = {
  run_id: 'r1',
  duration_ms_total: 1234,
  duration_ms_by_stage: {},
  llm_calls: 2,
  tokens_input: null,
  tokens_output: null,
  candidates_found: 1,
  candidates_excluded: 12,
  quotes_accepted: 1,
  quotes_rejected: 0,
  abstentions: 1,
  warnings: 0,
  errors: 0,
  status_counts: { DIRECT: 1 },
  computed_by: 'backend',
};

const EVENTS: PipelineEvent[] = [
  {
    event_id: 'e1', sequence: 1, event_type: 'RUN_CREATED',
    created_at: '2026-08-04T00:00:00Z', actor: 'orchestrator',
    stage_id: null, stage_type: null, producer: null,
    payload_hash: 'abcdef0123456789', payload: {},
  },
  {
    event_id: 'e2', sequence: 2, event_type: 'STAGE_COMPLETED',
    created_at: '2026-08-04T00:00:01Z', actor: 'kg_retrieval',
    stage_id: 'stage_5_kg_retrieval', stage_type: 'KG_RETRIEVAL',
    producer: { kind: 'DETERMINISTIC', component: 'kg', version: '1', model: null, prompt_version: null },
    payload_hash: 'fedcba9876543210', payload: {},
  },
];

describe('SupervisorPanel', () => {
  it('dichiara che le metriche sono canoniche e calcolate dal backend', () => {
    render(<SupervisorPanel metrics={METRICS} events={EVENTS} hashChainValid versions={{}} />);
    expect(screen.getByText(/Metriche canoniche — calcolate dal backend/)).toBeInTheDocument();
  });

  it('mostra “non disponibile” invece di zero per una misura mancante', () => {
    render(<SupervisorPanel metrics={METRICS} events={EVENTS} hashChainValid versions={{}} />);

    // I token non sono registrati: renderli 0 dichiarerebbe una misura mai presa.
    expect(screen.getAllByText('non disponibile').length).toBeGreaterThanOrEqual(2);
  });

  it('riporta lo stato della catena di hash', () => {
    render(<SupervisorPanel metrics={METRICS} events={EVENTS} hashChainValid versions={{}} />);
    expect(screen.getByText(/Catena di hash verificata/)).toBeInTheDocument();
  });

  it('segnala una catena non valida', () => {
    render(<SupervisorPanel metrics={METRICS} events={EVENTS} hashChainValid={false} versions={{}} />);
    expect(screen.getByText(/Catena di hash NON valida/)).toBeInTheDocument();
  });

  it('distingue una catena non verificata da una non valida', () => {
    render(<SupervisorPanel metrics={METRICS} events={EVENTS} hashChainValid={null} versions={{}} />);
    expect(screen.getByText(/Catena di hash non verificata/)).toBeInTheDocument();
  });

  it('elenca gli eventi con sequenza, tipo e producer', () => {
    render(<SupervisorPanel metrics={METRICS} events={EVENTS} hashChainValid versions={{}} />);

    expect(screen.getByText('RUN_CREATED')).toBeInTheDocument();
    expect(screen.getByText('stage_5_kg_retrieval')).toBeInTheDocument();
    expect(screen.getByText('DETERMINISTIC')).toBeInTheDocument();
  });

  it('mostra le versioni dei componenti', () => {
    render(<SupervisorPanel metrics={METRICS} events={EVENTS} hashChainValid
                            versions={{ orchestrator: 'research-pipeline-orchestrator/1.0' }} />);
    expect(screen.getByText(/orchestrator: research-pipeline-orchestrator\/1.0/)).toBeInTheDocument();
  });

  it('regge l’assenza di metriche', () => {
    render(<SupervisorPanel metrics={null} events={[]} hashChainValid={null} versions={{}} />);
    expect(screen.getByText('Nessun evento registrato.')).toBeInTheDocument();
  });
});
