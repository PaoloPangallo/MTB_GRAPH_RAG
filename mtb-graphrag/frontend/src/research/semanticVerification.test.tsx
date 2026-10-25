import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { ValidationStage } from './stages/EnrichmentStages';

it('rende esplicito il contributo LLM effettivamente invocato nella verifica', () => {
  render(<ValidationStage preview={{ validations: [], semantic_verification: {
    attempted_calls: 1, attempts: [{ model: 'controlled-model', prompt_version: '2.0' }],
    policy_version: 'evidence-drug-semantic-admission/2.0',
  } }} />);
  expect(screen.getByText('Confronto semantico LLM: 1 chiamata')).toBeInTheDocument();
  expect(screen.getByText(/Le interpretazioni del modello restano fallibili/)).toBeInTheDocument();
  expect(screen.getByText('controlled-model')).toBeInTheDocument();
  expect(screen.getByText('evidence-drug-semantic-admission/2.0')).toBeInTheDocument();
});

it('spiega i blocker senza ricalcolare il verdetto', () => {
  render(<ValidationStage preview={{ validations: [{
    document_verification: { admission_reason_codes: ['SEMANTIC_INFERENCE_INVERSE'] },
  }] }} />);
  expect(screen.getByText('La relazione richiederebbe un’inferenza inversa non dimostrata')).toBeInTheDocument();
});

it('non mostra contributo LLM quando le invocazioni sono zero', () => {
  render(<ValidationStage preview={{ validations: [], semantic_verification: { attempted_calls: 0 } }} />);
  expect(screen.queryByText(/Confronto semantico LLM:/)).not.toBeInTheDocument();
});

it('non attribuisce una chiamata live a una preview storica o senza confronto', () => {
  render(<ValidationStage preview={{ validations: [] }} />);
  expect(screen.queryByText(/Confronto semantico LLM:/)).not.toBeInTheDocument();
});
