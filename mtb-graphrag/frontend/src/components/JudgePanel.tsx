import { 
  Card, 
  CardContent, 
  CardHeader, 
  Typography, 
  Box, 
  Grid,
  Rating
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
    <Card variant="outlined" sx={{ mt: 3, bgcolor: '#F8FAFC' }}>
      <CardHeader 
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <GavelIcon color="primary" />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>LLM-as-Judge Evaluation</Typography>
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1, bgcolor: 'background.paper', borderRadius: 1, border: '1px solid #E2E8F0' }}>
            <Typography variant="h5" color="primary.main" sx={{ fontWeight: 700 }}>
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
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Criterion label="Completezza (Comprehensiveness)" score={judgeData.completezza} />
              <Criterion label="Utilità clinica (Clinical Actionability)" score={judgeData.utilita_clinica} />
              <Criterion label="Fedeltà evidenze (Evidence Faithfulness)" score={judgeData.fedelta_evidenze} />
              <Criterion label="Accuratezza clinica (Clinical Accuracy)" score={judgeData.accuratezza_clinica} />
            </Box>
          </Grid>
          <Grid size={{ xs: 12, md: 6 }}>
            <Box sx={{ height: '100%', p: 2, bgcolor: 'background.paper', borderRadius: 1, border: '1px solid #E2E8F0' }}>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                RATIONALE
              </Typography>
              <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                "{judgeData.motivazione}"
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}

function Criterion({ label, score }: { label: string, score?: number }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <Typography variant="body2" sx={{ fontWeight: 500 }}>{label}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Rating value={score || 0} readOnly max={5} size="small" />
        <Typography variant="caption" color="text.secondary" sx={{ minWidth: 20 }}>
          {score}
        </Typography>
      </Box>
    </Box>
  );
}
