import React from 'react';
import { Box, Card, CardContent, Typography, Chip, Grid } from '@mui/material';
import type { V3RetrievalResponse, V3MetadataResponse } from '../../types/v3Types';

interface V3SummaryHeaderProps {
  result: V3RetrievalResponse;
  metadata?: V3MetadataResponse | null;
}

export const V3SummaryHeader: React.FC<V3SummaryHeaderProps> = ({ result, metadata }) => {
  if (!result || !result.summary) return null;

  const { summary, metadata: resMeta } = result;

  const corpusVersion = metadata?.corpus_version || resMeta?.corpus_version || 'qualified_claim_repository/1.4';
  const gateVersion = metadata?.gate_version || resMeta?.gate_version || 'qualified_claim_structural_gate/1.3';
  const policyMode = metadata?.policy_mode || resMeta?.policy_mode || 'strict_verified';
  const elapsedMs = resMeta?.elapsed_ms ?? 35;

  return (
    <Card
      variant="outlined"
      sx={{
        borderRadius: 2,
        borderColor: '#E2E8F0',
        mb: 2.5,
        bgcolor: '#FFFFFF',
        boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
      }}
    >
      <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1.5, mb: 2 }}>
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '1.1rem', letterSpacing: '-0.01em' }}>
              MTB-GraphRAG V3
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mt: 0.25 }}>
              Recupero e qualificazione claim-level delle evidenze oncologiche | Corpus: <code style={{ fontFamily: 'monospace', color: '#334155' }}>{corpusVersion}</code> | Gate: <code style={{ fontFamily: 'monospace', color: '#334155' }}>{gateVersion}</code>
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Chip
              label="V3 LIVE RETRIEVER"
              size="small"
              color="primary"
              variant="outlined"
              sx={{
                fontWeight: 700,
                fontSize: '0.72rem',
              }}
            />
          </Box>
        </Box>

        {/* METRICS ROW - REAL RETRIEVAL SUMMARY */}
        <Grid container spacing={1.5} sx={{ alignItems: 'center' }}>
          <Grid size={{ xs: 12, sm: 6, md: 2.4 }}>
            <Box sx={{ p: 1.5, borderRadius: 1.5, bgcolor: '#F8FAFC', border: '1px solid #E2E8F0', textAlign: 'center' }}>
              <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>
                Candidati Totali
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#0F172A', mt: 0.25 }}>
                {summary.total ?? 0}
              </Typography>
            </Box>
          </Grid>

          <Grid size={{ xs: 6, sm: 3, md: 2.4 }}>
            <Box sx={{ p: 1.5, borderRadius: 1.5, bgcolor: '#F0FDF4', border: '1px solid #DCFCE7', textAlign: 'center' }}>
              <Typography variant="caption" sx={{ color: '#166534', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>
                Primary
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#15803D', mt: 0.25 }}>
                {summary.primary ?? 0}
              </Typography>
            </Box>
          </Grid>

          <Grid size={{ xs: 6, sm: 3, md: 2.4 }}>
            <Box sx={{ p: 1.5, borderRadius: 1.5, bgcolor: '#FFFBEB', border: '1px solid #FEF3C7', textAlign: 'center' }}>
              <Typography variant="caption" sx={{ color: '#92400E', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>
                Warning
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#B45309', mt: 0.25 }}>
                {summary.warning ?? 0}
              </Typography>
            </Box>
          </Grid>

          <Grid size={{ xs: 6, sm: 3, md: 2.4 }}>
            <Box sx={{ p: 1.5, borderRadius: 1.5, bgcolor: '#FAF5FF', border: '1px solid #F3E8FF', textAlign: 'center' }}>
              <Typography variant="caption" sx={{ color: '#6B21A8', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>
                Audit
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#7E22CE', mt: 0.25 }}>
                {summary.audit ?? 0}
              </Typography>
            </Box>
          </Grid>

          <Grid size={{ xs: 6, sm: 3, md: 2.4 }}>
            <Box sx={{ p: 1.5, borderRadius: 1.5, bgcolor: '#FEF2F2', border: '1px solid #FEE2E2', textAlign: 'center' }}>
              <Typography variant="caption" sx={{ color: '#991B1B', fontWeight: 600, fontSize: '0.7rem', textTransform: 'uppercase' }}>
                Rejected
              </Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: '#DC2626', mt: 0.25 }}>
                {summary.rejected ?? 0}
              </Typography>
            </Box>
          </Grid>
        </Grid>

        <Box sx={{ mt: 1.5, pt: 1, borderTop: '1px solid #F1F5F9', display: 'flex', justifyContent: 'space-between', color: '#64748B', fontSize: '0.75rem' }}>
          <span>Latenza Pipeline: <strong>{elapsedMs} ms</strong></span>
          <span>Policy Mode: <code style={{ fontFamily: 'monospace' }}>{policyMode}</code></span>
        </Box>
      </CardContent>
    </Card>
  );
};

export default V3SummaryHeader;
