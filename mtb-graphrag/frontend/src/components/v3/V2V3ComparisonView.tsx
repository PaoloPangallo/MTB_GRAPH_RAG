import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Button,
  Chip,
  Alert,
  Divider,
  Paper,
  Stack,
  CircularProgress,
  TextField,
} from '@mui/material';
import ReactMarkdown from 'react-markdown';
import { retrieveV3Evidence } from '../../api/v3Api';
import type { V3RetrievalResponse } from '../../types/v3Types';

interface V2Response {
  report: string;
  cited_pmids: number[];
  drug_candidates: Array<{ drug_name: string; [key: string]: any }>;
  execution_time_ms?: number;
}

export const V2V3ComparisonView: React.FC = () => {
  const [biomarker, setBiomarker] = useState('EGFR L858R');
  const [disease, setDisease] = useState('Non-Small Cell Lung Cancer');
  const [intervention, setIntervention] = useState('Osimertinib');

  const [loading, setLoading] = useState(false);
  const [errorV2, setErrorV2] = useState<string | null>(null);
  const [errorV3, setErrorV3] = useState<string | null>(null);

  const [v2Result, setV2Result] = useState<V2Response | null>(null);
  const [v3Result, setV3Result] = useState<V3RetrievalResponse | null>(null);
  const [v2TimeMs, setV2TimeMs] = useState<number>(0);

  const handleRunRealComparison = async () => {
    setLoading(true);
    setErrorV2(null);
    setErrorV3(null);
    setV2Result(null);
    setV3Result(null);

    const baseUrl = (import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000';

    // 1. Chiamata Reale V2 (/api/v1/analyze)
    const startTimeV2 = performance.now();
    try {
      const v2Res = await fetch(`${baseUrl}/api/v1/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gene: biomarker.split(' ')[0] || 'EGFR',
          variant: biomarker,
          tumor_type: disease,
        }),
      });
      const endTimeV2 = performance.now();
      setV2TimeMs(Math.round(endTimeV2 - startTimeV2));

      if (!v2Res.ok) {
        const text = await v2Res.text().catch(() => v2Res.statusText);
        throw new Error(`Errore HTTP ${v2Res.status}: ${text}`);
      }
      const dataV2 = await v2Res.json();
      setV2Result(dataV2);
    } catch (err: any) {
      setErrorV2(`V2 non disponibile: ${err.message}`);
    }

    // 2. Chiamata Reale V3 (/api/v1/v3/retrieve)
    try {
      const dataV3 = await retrieveV3Evidence({
        domain: 'therapeutic',
        biomarker,
        disease,
        intervention: intervention || undefined,
      });
      setV3Result(dataV3);
    } catch (err: any) {
      setErrorV3(`V3 non disponibile: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ flexGrow: 1, py: 1 }}>
      {/* MANDATORY DISCLAIMER NOTE */}
      <Alert severity="info" variant="outlined" sx={{ mb: 2.5, fontWeight: 600, fontSize: '0.82rem', borderColor: '#CBD5E1', color: '#334155', bgcolor: '#F8FAFC' }}>
        Il confronto descrive l’evoluzione della rappresentazione delle evidenze. Non costituisce l’esperimento principale della tesi.
      </Alert>

      {/* COMPARISON INPUT FORM */}
      <Card variant="outlined" sx={{ mb: 2.5, borderRadius: 2, borderColor: '#E2E8F0', bgcolor: '#FFFFFF' }}>
        <CardContent sx={{ p: 2.5 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '0.95rem', mb: 2 }}>
            Confronto Esecutivo Reale V2 ↔ V3
          </Typography>

          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid size={{ xs: 12, md: 4 }}>
              <TextField
                label="Biomarcatore"
                size="small"
                fullWidth
                value={biomarker}
                onChange={(e) => setBiomarker(e.target.value)}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              <TextField
                label="Patologia"
                size="small"
                fullWidth
                value={disease}
                onChange={(e) => setDisease(e.target.value)}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              <TextField
                label="Intervento"
                size="small"
                fullWidth
                value={intervention}
                onChange={(e) => setIntervention(e.target.value)}
              />
            </Grid>
          </Grid>

          <Button
            variant="contained"
            color="primary"
            onClick={handleRunRealComparison}
            disabled={loading}
            sx={{ textTransform: 'none', fontWeight: 600 }}
          >
            {loading ? 'Esecuzione confronto in corso...' : 'Esegui Confronto Reale V2 ↔ V3'}
          </Button>
        </CardContent>
      </Card>

      {/* SIDE-BY-SIDE COMPARISON RESULTS */}
      <Grid container spacing={2.5}>
        {/* COLONNA V2 */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ borderRadius: 2, borderColor: '#CBD5E1', height: '100%', bgcolor: '#FFFFFF' }}>
            <CardContent sx={{ p: 2.5 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#475569', fontSize: '0.9rem' }}>
                  V2: Record-centric
                </Typography>
                <Chip label="Endpoint /analyze" size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 20 }} />
              </Box>
              <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mb: 1.5 }}>
                Flusso: record/fonti recuperati ➔ report testuale LLM
              </Typography>

              <Divider sx={{ mb: 2 }} />

              {loading ? (
                <Box sx={{ p: 4, textAlign: 'center' }}>
                  <CircularProgress size={28} />
                </Box>
              ) : errorV2 ? (
                <Alert severity="error" sx={{ my: 1 }}>{errorV2}</Alert>
              ) : v2Result ? (
                <>
                  <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', textTransform: 'uppercase', display: 'block', mb: 0.5 }}>
                    Latenza Reale V2:
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, mb: 2, fontSize: '0.85rem' }}>
                    {v2TimeMs} ms
                  </Typography>

                  <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', textTransform: 'uppercase', display: 'block', mb: 0.5 }}>
                    PMID Citati Reali ({v2Result.cited_pmids?.length || 0}):
                  </Typography>
                  <Stack direction="row" spacing={0.5} sx={{ mb: 2, flexWrap: 'wrap' }}>
                    {(v2Result.cited_pmids || []).map((pmid, idx) => (
                      <Chip key={idx} label={`PMID: ${pmid}`} size="small" variant="outlined" sx={{ fontSize: '0.68rem' }} />
                    ))}
                  </Stack>

                  <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', textTransform: 'uppercase', display: 'block', mb: 0.5 }}>
                    Report Testuale Reale V2:
                  </Typography>
                  <Paper variant="outlined" sx={{ p: 1.75, bgcolor: '#F8FAFC', borderRadius: 1, borderColor: '#E2E8F0', fontSize: '0.82rem' }}>
                    <ReactMarkdown>{v2Result.report}</ReactMarkdown>
                  </Paper>
                </>
              ) : (
                <Typography variant="caption" sx={{ color: '#94A3B8', fontStyle: 'italic' }}>
                  Fai clic su "Esegui Confronto Reale V2 ↔ V3" per interrogare l'endpoint V2 live.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* COLONNA V3 */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card variant="outlined" sx={{ borderRadius: 2, borderColor: '#93C5FD', height: '100%', bgcolor: '#FFFFFF' }}>
            <CardContent sx={{ p: 2.5 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#1E40AF', fontSize: '0.9rem' }}>
                  V3: Evidence-centric
                </Typography>
                <Chip label="Endpoint /api/v1/v3/retrieve" size="small" color="primary" sx={{ fontWeight: 700, fontSize: '0.68rem', height: 20 }} />
              </Box>
              <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mb: 1.5 }}>
                Flusso: qualified claims ➔ gate ➔ 4 bucket ➔ provenance ➔ report opzionale
              </Typography>

              <Divider sx={{ mb: 2 }} />

              {loading ? (
                <Box sx={{ p: 4, textAlign: 'center' }}>
                  <CircularProgress size={28} />
                </Box>
              ) : errorV3 ? (
                <Alert severity="error" sx={{ my: 1 }}>{errorV3}</Alert>
              ) : v3Result ? (
                <>
                  <Typography variant="caption" sx={{ fontWeight: 700, color: '#1E40AF', textTransform: 'uppercase', display: 'block', mb: 0.5 }}>
                    Conteggi Reali nei 4 Bucket V3:
                  </Typography>
                  <Grid container spacing={1} sx={{ mb: 2 }}>
                    <Grid size={{ xs: 3 }}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center', bgcolor: '#F0FDF4', borderColor: '#DCFCE7' }}>
                        <Typography variant="caption" sx={{ color: '#166534', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>PRIMARY</Typography>
                        <Typography variant="subtitle1" sx={{ color: '#15803D', fontWeight: 700 }}>{v3Result.summary?.primary ?? 0}</Typography>
                      </Paper>
                    </Grid>
                    <Grid size={{ xs: 3 }}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center', bgcolor: '#FFFBEB', borderColor: '#FEF3C7' }}>
                        <Typography variant="caption" sx={{ color: '#92400E', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>WARNING</Typography>
                        <Typography variant="subtitle1" sx={{ color: '#B45309', fontWeight: 700 }}>{v3Result.summary?.warning ?? 0}</Typography>
                      </Paper>
                    </Grid>
                    <Grid size={{ xs: 3 }}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center', bgcolor: '#FAF5FF', borderColor: '#F3E8FF' }}>
                        <Typography variant="caption" sx={{ color: '#6B21A8', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>AUDIT</Typography>
                        <Typography variant="subtitle1" sx={{ color: '#7E22CE', fontWeight: 700 }}>{v3Result.summary?.audit ?? 0}</Typography>
                      </Paper>
                    </Grid>
                    <Grid size={{ xs: 3 }}>
                      <Paper variant="outlined" sx={{ p: 1, textAlign: 'center', bgcolor: '#FEF2F2', borderColor: '#FEE2E2' }}>
                        <Typography variant="caption" sx={{ color: '#991B1B', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>REJECTED</Typography>
                        <Typography variant="subtitle1" sx={{ color: '#DC2626', fontWeight: 700 }}>{v3Result.summary?.rejected ?? 0}</Typography>
                      </Paper>
                    </Grid>
                  </Grid>

                  <Typography variant="caption" sx={{ fontWeight: 700, color: '#1E40AF', textTransform: 'uppercase', display: 'block', mb: 0.5 }}>
                    Latenza Pipeline Reale V3:
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, mb: 2, fontSize: '0.85rem' }}>
                    {v3Result.metadata?.elapsed_ms ?? 0} ms
                  </Typography>

                  <Typography variant="caption" sx={{ fontWeight: 700, color: '#1E40AF', textTransform: 'uppercase', display: 'block', mb: 0.5 }}>
                    Prime Claim Qualificate Reali (Primary):
                  </Typography>
                  <Stack spacing={1} sx={{ mb: 2 }}>
                    {(v3Result.buckets?.primary || []).slice(0, 3).map((claim) => (
                      <Paper key={claim.claim_id} variant="outlined" sx={{ p: 1.25, bgcolor: '#F8FAFC', borderRadius: 1, borderColor: '#E2E8F0' }}>
                        <Typography variant="body2" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '0.82rem' }}>
                          {claim.biomarker} ➔ {claim.canonical_intervention} ({claim.disease_scope})
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#64748B', fontFamily: 'monospace', display: 'block' }}>
                          ID: {claim.claim_id} | Score: {typeof claim.score === 'object' && claim.score ? (claim.score as any).total_score?.toFixed(3) : '0.000'}
                        </Typography>
                      </Paper>
                    ))}
                  </Stack>
                </>
              ) : (
                <Typography variant="caption" sx={{ color: '#94A3B8', fontStyle: 'italic' }}>
                  Fai clic su "Esegui Confronto Reale V2 ↔ V3" per interrogare l'endpoint V3 live.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default V2V3ComparisonView;
