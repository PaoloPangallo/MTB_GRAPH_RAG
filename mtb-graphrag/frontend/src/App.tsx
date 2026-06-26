import { useState } from 'react';
import { 
  Box, 
  Container, 
  Grid, 
  Typography, 
  AppBar, 
  Toolbar,
  CircularProgress,
  Alert
} from '@mui/material';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import InputForm from './components/InputForm';
import ReportView from './components/ReportView';
import StructuredData from './components/StructuredData';
import JudgePanel from './components/JudgePanel';
import type { MTBRequest, ReportResponse, JudgeResponse } from './types';

function App() {
  const [loading, setLoading] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [isZeroShotMode, setIsZeroShotMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportData, setReportData] = useState<ReportResponse | null>(null);
  const [zeroShotData, setZeroShotData] = useState<ReportResponse | null>(null);
  const [judgeData, setJudgeData] = useState<JudgeResponse | null>(null);
  const [lastRequest, setLastRequest] = useState<MTBRequest | null>(null);

  const [compareMode, setCompareMode] = useState(false);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [loadingZero, setLoadingZero] = useState(false);

  const handleAnalyze = async (req: MTBRequest, isZeroShot: boolean = false) => {
    setCompareMode(false);
    setLoading(true);
    setIsZeroShotMode(isZeroShot);
    setError(null);
    setReportData(null);
    setZeroShotData(null);
    setJudgeData(null);
    setLastRequest(req);
    
    try {
      const endpoint = isZeroShot ? 'zeroshot' : 'analyze';
      const res = await fetch(`http://localhost:8000/api/v1/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req)
      });
      if (!res.ok) throw new Error(`Errore durante la generazione (${isZeroShot ? 'Zero-shot' : 'GraphRAG'})`);
      const data: ReportResponse = await res.json();
      setReportData(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async (req: MTBRequest) => {
    setCompareMode(true);
    setLoadingGraph(true);
    setLoadingZero(true);
    setError(null);
    setReportData(null);
    setZeroShotData(null);
    setJudgeData(null);
    setLastRequest(req);

    const runGraphRAG = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/v1/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(req)
        });
        if (!res.ok) throw new Error('Errore nella generazione GraphRAG');
        const data: ReportResponse = await res.json();
        setReportData(data);
      } catch (err: any) {
        setError(prev => prev ? `${prev} | ${err.message}` : err.message);
      } finally {
        setLoadingGraph(false);
      }
    };

    const runZeroShot = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/v1/zeroshot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(req)
        });
        if (!res.ok) throw new Error('Errore nella generazione Zero-shot');
        const data: ReportResponse = await res.json();
        setZeroShotData(data);
      } catch (err: any) {
        setError(prev => prev ? `${prev} | ${err.message}` : err.message);
      } finally {
        setLoadingZero(false);
      }
    };

    Promise.all([runGraphRAG(), runZeroShot()]);
  };

  const handleEnrich = async () => {
    if (!lastRequest || !reportData) return;
    setEnriching(true);
    try {
      const reqWithEnrich = { 
        ...lastRequest, 
        enrich_with_oncokb: true, 
        report: reportData.report 
      };
      const res = await fetch('http://localhost:8000/api/v1/enrich', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqWithEnrich)
      });
      if (!res.ok) throw new Error('Errore durante l\'enrichment OncoKB');
      const enrichedData: ReportResponse = await res.json();
      // Aggiorniamo sia il report con l'integrazione clinica sia l'enrichment in appendice
      setReportData(prev => prev ? { 
        ...prev, 
        report: enrichedData.report, 
        oncokb_enrichment: enrichedData.oncokb_enrichment 
      } : enrichedData);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setEnriching(false);
    }
  };

  const handleJudge = async () => {
    if (!lastRequest || !reportData) return;
    try {
      const res = await fetch('http://localhost:8000/api/v1/judge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          report: reportData.report,
          gene: lastRequest.gene,
          variant: lastRequest.variant,
          tumor_type: lastRequest.tumor_type
        })
      });
      if (!res.ok) throw new Error('Errore durante la valutazione LLM-as-judge');
      const data: JudgeResponse = await res.json();
      setJudgeData(data);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <AppBar position="static" elevation={0} sx={{ borderBottom: '1px solid #E2E8F0' }}>
        <Toolbar>
          <LocalHospitalIcon sx={{ mr: 2 }} />
          <Typography variant="h6" component="div" sx={{ flexGrow: 1, fontWeight: 600 }}>
            MTB GraphRAG Assistant
          </Typography>
        </Toolbar>
      </AppBar>

      <Container maxWidth="xl" sx={{ flexGrow: 1, py: 4 }}>
        <Grid container spacing={4}>
          <Grid size={{ xs: 12, md: 4, lg: 3 }}>
            <InputForm 
              onSubmit={handleAnalyze} 
              onCompare={handleCompare}
              disabled={loading || loadingGraph || loadingZero} 
            />
          </Grid>
          
          <Grid size={{ xs: 12, md: 8, lg: 9 }}>
            {error && (
              <Alert severity="error" sx={{ mb: 3 }}>
                {error}
              </Alert>
            )}

            {compareMode ? (
              <Grid container spacing={3}>
                {/* Colonna Sinistra: GraphRAG */}
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" color="primary.main" gutterBottom sx={{ fontWeight: 600, mb: 2 }}>
                    1. Sistema GraphRAG (Conoscenza Strutturata)
                  </Typography>
                  {loadingGraph ? (
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 10, border: '1px dashed #CBD5E1', borderRadius: 2, bgcolor: 'background.paper' }}>
                      <CircularProgress size={40} thickness={4} color="primary" />
                      <Typography variant="body1" sx={{ mt: 2, color: 'text.secondary' }}>
                        Consultazione Knowledge Graph in corso...
                      </Typography>
                    </Box>
                  ) : reportData ? (
                    <ReportView 
                      data={reportData} 
                      onEnrich={handleEnrich} 
                      enriching={enriching} 
                    />
                  ) : (
                    <Box sx={{ py: 5, textAlign: 'center', color: 'text.secondary' }}>Nessun dato generato per GraphRAG</Box>
                  )}
                </Grid>

                {/* Colonna Destra: Zero-Shot */}
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" color="secondary.main" gutterBottom sx={{ fontWeight: 600, mb: 2 }}>
                    2. Baseline Zero-Shot (Memoria Parametrica)
                  </Typography>
                  {loadingZero ? (
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 10, border: '1px dashed #CBD5E1', borderRadius: 2, bgcolor: 'background.paper' }}>
                      <CircularProgress size={40} thickness={4} color="secondary" />
                      <Typography variant="body1" sx={{ mt: 2, color: 'text.secondary' }}>
                        Generazione LLM Zero-shot in corso...
                      </Typography>
                    </Box>
                  ) : zeroShotData ? (
                    <ReportView 
                      data={zeroShotData} 
                      onEnrich={() => {}} 
                      enriching={false} 
                    />
                  ) : (
                    <Box sx={{ py: 5, textAlign: 'center', color: 'text.secondary' }}>Nessun dato generato per Zero-Shot</Box>
                  )}
                </Grid>
                
                {reportData && !loadingGraph && (
                  <Grid size={{ xs: 12 }} sx={{ mt: 2 }}>
                    <StructuredData data={reportData} onEnrich={handleEnrich} enriching={enriching} />
                  </Grid>
                )}
              </Grid>
            ) : loading ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 10 }}>
                <CircularProgress size={60} thickness={4} color={isZeroShotMode ? "secondary" : "primary"} />
                <Typography variant="h6" sx={{ mt: 3, color: 'text.secondary' }}>
                  {isZeroShotMode ? "Generazione report Zero-Shot..." : "Elaborazione pipeline agentica GraphRAG..."}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1 }}>
                  {isZeroShotMode 
                    ? "L'LLM sta generando il report basandosi unicamente sulla sua memoria parametrica." 
                    : "L'agente sta consultando il Knowledge Graph e sintetizzando le evidenze."}
                </Typography>
              </Box>
            ) : reportData ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <ReportView 
                  data={reportData} 
                  onEnrich={handleEnrich} 
                  enriching={enriching} 
                />
                <StructuredData data={reportData} onEnrich={handleEnrich} enriching={enriching} />                {judgeData ? (
                  <JudgePanel judgeData={judgeData} />
                ) : (
                  <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                    <Typography 
                      variant="button" 
                      onClick={handleJudge}
                      sx={{ color: 'primary.main', cursor: 'pointer', textDecoration: 'underline' }}
                    >
                      Richiedi valutazione indipendente LLM-as-judge
                    </Typography>
                  </Box>
                )}
              </Box>
            ) : (
              <Box sx={{ 
                height: '100%', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                border: '1px dashed #CBD5E1',
                borderRadius: 2,
                bgcolor: 'background.paper',
                p: 5
              }}>
                <Typography variant="h5" color="text.secondary" align="center">
                  Inserisci i dati clinici nel modulo a sinistra per generare un report MTB.
                </Typography>
              </Box>
            )}
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
}

export default App;
