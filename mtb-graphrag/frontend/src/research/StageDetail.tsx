import { useEffect, useState } from 'react';
import { Alert, Box, Typography } from '@mui/material';
import { getStage } from './api';
import StageInspector from './StageInspector';
import type { PipelineEvent, PipelineStage } from './types';

interface Props {
  runId: string;
  stage: PipelineStage | null;
  events: PipelineEvent[];
  clinicalText?: string;
}

export default function StageDetail({ runId, stage, events, clinicalText }: Props) {
  const [result, setResult] = useState<{ key: string; stage?: PipelineStage; error?: string } | null>(null);
  const stageId = stage?.stage_id;
  const status = stage?.status;
  const key = `${runId}:${stageId}:${status}`;
  useEffect(() => {
    if (!stageId) return;
    let active = true;
    void (async () => {
      try {
        const response = await getStage(runId, stageId);
        if (active) setResult({ key, stage: response.stage });
      } catch {
        if (active) setResult({ key, error: 'Output completo non disponibile. Sono mostrati i metadati dello stage.' });
      }
    })();
    return () => { active = false; };
  }, [runId, stageId, status, key]);
  const current = result?.key === key ? result : null;
  return <Box>
    {stage && !current && <Typography role="status" sx={{ px: 3, pt: 2 }}>Caricamento dell’output dello stage…</Typography>}
    {current?.error && <Alert severity="warning">{current.error}</Alert>}
    <StageInspector stage={current?.stage ?? stage} events={events} clinicalText={clinicalText} />
  </Box>;
}
