import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Box,
  Grid,
  Rating,
  LinearProgress,
} from '@mui/material';
import GavelIcon from '@mui/icons-material/Gavel';
import type { JudgeResponse } from '../types';

interface JudgePanelProps {
  judgeData: JudgeResponse;
}

export default function JudgePanel({ judgeData }: JudgePanelProps) {
  if (judgeData.error) {
    return (
      <Card variant="outlined" sx={{ mt: 3, borderColor: 'error.main' }}>
        <CardContent>
          <Typography color="error">Errore Judge: {judgeData.error}</Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card variant="outlined" sx={{ mt: 3, bgcolor: '#F8FAFC', borderTop: '3px solid', borderTopColor: 'primary.main' }}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <GavelIcon color="primary" />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>LLM-as-Judge Evaluation</Typography>
          </Box>
        }
        action={
          <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 0.5,
            px: 2.5,
            py: 1.5,
            bgcolor: 'primary.light',
            borderRadius: 2,
            border: '1px solid #BFDBFE',
            minWidth: 100,
          }}>
            <Typography variant="caption" sx={{ fontWeight: 600, color: 'primary.dark', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              Score
            </Typography>
            <Typography variant="h4" color="primary.dark" sx={{ fontWeight: 800, lineHeight: 1 }}>
              {judgeData.score_totale?.toFixed(1)}
            </Typography>
            <Rating value={judgeData.score_totale || 0} precision={0.1} readOnly size="small" />
          </Box>
        }
        sx={{ borderBottom: '1px solid #E2E8F0', pb: 2 }}
      />
      <CardContent>
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
              <Criterion label="Completezza (Comprehensiveness)" score={judgeData.completezza} />
              <Criterion label="Utilità clinica (Clinical Actionability)" score={judgeData.utilita_clinica} />
              <Criterion label="Fedeltà evidenze (Evidence Faithfulness)" score={judgeData.fedelta_evidenze} />
              <Criterion label="Accuratezza clinica (Clinical Accuracy)" score={judgeData.accuratezza_clinica} />
            </Box>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Box sx={{ height: '100%', p: 2.5, bgcolor: 'background.paper', borderRadius: 2, border: '1px solid #E2E8F0' }}>
              <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', letterSpacing: '0.06em', textTransform: 'uppercase', display: 'block', mb: 1.5 }}>
                Rationale
              </Typography>
              <Typography variant="body2" sx={{ fontStyle: 'italic', color: '#334155', lineHeight: 1.7 }}>
                "{judgeData.motivazione}"
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}

function getProgressColor(score: number): 'success' | 'warning' | 'error' | 'primary' {
  if (score >= 4) return 'success';
  if (score >= 3) return 'primary';
  if (score >= 2) return 'warning';
  return 'error';
}

function Criterion({ label, score }: { label: string; score?: number }) {
  const value = score ?? 0;
  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.75 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, color: '#1E293B' }}>{label}</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Rating value={value} readOnly max={5} size="medium" />
          <Typography variant="body2" sx={{ fontWeight: 700, color: 'primary.main', minWidth: 24, textAlign: 'right' }}>
            {value}
          </Typography>
        </Box>
      </Box>
      <LinearProgress
        variant="determinate"
        value={(value / 5) * 100}
        color={getProgressColor(value)}
        sx={{ height: 5, borderRadius: 3, bgcolor: '#E2E8F0' }}
      />
    </Box>
  );
}
