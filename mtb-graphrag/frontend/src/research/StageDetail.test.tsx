import { act, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import StageDetail from './StageDetail';
import { getStage } from './api';
import { makeStage } from './testFactories';

vi.mock('./api', () => ({ getStage: vi.fn() }));
vi.mock('./StageInspector', () => ({ default: ({ stage }: { stage: { stage_id: string } }) => <div>{stage.stage_id}</div> }));

it('non mostra la risposta lenta del precedente stage dopo una nuova selezione', async () => {
  let resolve!: (value: Awaited<ReturnType<typeof getStage>>) => void;
  vi.mocked(getStage).mockReturnValueOnce(new Promise(done => { resolve = done; }))
    .mockResolvedValueOnce({ stage: makeStage({ stage_id: 'stage-b' }) });
  const { rerender } = render(<StageDetail runId="r1" stage={makeStage({ stage_id: 'stage-a' })} events={[]} />);
  rerender(<StageDetail runId="r1" stage={makeStage({ stage_id: 'stage-b' })} events={[]} />);
  await screen.findByText('stage-b');
  await act(async () => { resolve({ stage: makeStage({ stage_id: 'stage-a' }) }); });
  expect(screen.queryByText('stage-a')).not.toBeInTheDocument();
  expect(screen.getByText('stage-b')).toBeInTheDocument();
});
