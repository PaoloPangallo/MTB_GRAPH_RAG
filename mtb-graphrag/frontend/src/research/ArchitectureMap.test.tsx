import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import ArchitectureMap from './ArchitectureMap';
import { makeStage } from './testFactories';

it('distingue i tre percorsi e collega solo gli stage presenti all’ispezione', () => {
  const onSelect = vi.fn();
  render(<ArchitectureMap stages={[makeStage({ stage_id: 'stage_2_casecontext_parser' })]} selectedStageId={null} onSelect={onSelect} />);
  expect(screen.getByRole('heading', { name: 'PAPER · Pubblicazioni' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'TRIAL · Studi clinici' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'KG_ONLY · Relazioni del grafo' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Estrazione/ }));
  expect(onSelect).toHaveBeenCalledWith('stage_2_casecontext_parser');
  expect(screen.getByRole('button', { name: /Reader/ })).toBeDisabled();
});
