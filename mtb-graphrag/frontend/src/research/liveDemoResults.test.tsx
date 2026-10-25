import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import casesResponse from './__fixtures__/demo-cases.json';
import results from './__fixtures__/live-demo-results.json';
import CaseInputPanel from './CaseInputPanel';
import StageOutput from './stages';
import type { PipelineStage } from './types';

describe('casi frontend eseguiti sul runtime live', () => {
  for (const demo of casesResponse.cases) {
    it(`invia esattamente la chiave API del caso ${demo.case_id}`, () => {
      const onRun = vi.fn();
      render(<CaseInputPanel cases={[demo]} observedCases={[]} busy={false} onRun={onRun} />);
      fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Scegli un caso di esempio' }));
      fireEvent.click(screen.getByRole('option', { selected: false }));
      expect(screen.getByLabelText('Testo clinico in linguaggio libero')).toHaveValue(demo.clinical_text);
      fireEvent.click(screen.getByRole('button', { name: 'Esegui la pipeline' }));
      expect(onRun).toHaveBeenCalledWith({ demo_case_key: demo.case_id });
    });
  }
  for (const result of results) {
    it(`mostra la causa reale del fallimento parser di ${result.case_id}`, () => {
      expect(result.status).toBe('FAILED');
      expect(result.stopped_at).toBe('PARSER_TRANSPORT_FAILED');
      render(<StageOutput stage={result.parser_stage as PipelineStage} />);
      expect(screen.getByText('TARGET_INTERVENTION_KEYS_INVALID')).toBeInTheDocument();
      expect(screen.getByText('INVALID_TOOL_ARGUMENTS')).toBeInTheDocument();
      expect(screen.getByText('200')).toBeInTheDocument();
      expect(screen.queryByText(/Strong structural match/)).not.toBeInTheDocument();
    });
  }
});
