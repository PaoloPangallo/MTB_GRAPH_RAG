import { useState } from 'react';
import { 
  Box, 
  Container, 
  Grid, 
  Typography, 
  AppBar, 
  Toolbar,
  CircularProgress,
  Alert,
  Card,
  CardContent,
  Chip
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
  const [selectedConditions, setSelectedConditions] = useState<string[]>(['vanilla', 'full_graphrag']);
  const [compareResults, setCompareResults] = useState<Record<string, ReportResponse | null>>({
    vanilla: null,
    websearch: null,
    rag_testuale: null,
    full_graphrag: null,
  });
  const [compareLoadings, setCompareLoadings] = useState<Record<string, boolean>>({
    vanilla: false,
    websearch: false,
    rag_testuale: false,
    full_graphrag: false,
  });
  const [compareErrors, setCompareErrors] = useState<Record<string, string | null>>({
    vanilla: null,
    websearch: null,
    rag_testuale: null,
    full_graphrag: null,
  });

  const isCompareLoading = Object.values(compareLoadings).some(Boolean);

  const getExtractedDrugs = (reportText: string, candidates: any[]) => {
    if (candidates && candidates.length > 0) {
      return candidates.map(c => c.drug_name);
    }
    const DRUGS = [
      'osimertinib', 'erlotinib', 'gefitinib', 'dacomitinib', 'afatinib',
      'alectinib', 'crizotinib', 'lorlatinib', 'ceritinib', 'brigatinib',
      'vemurafenib', 'dabrafenib', 'trametinib', 'encorafenib', 'binimetinib', 'cobimetinib',
      'trastuzumab', 'pertuzumab', 'lapatinib', 'neratinib', 'tucatinib',
      'imatinib', 'dasatinib', 'nilotinib', 'bosutinib', 'ponatinib', 'asciminib',
      'olaparib', 'rucaparib', 'niraparib', 'talazoparib',
      'pembrolizumab', 'nivolumab', 'atezolizumab', 'durvalumab', 'avelumab',
      'alpelisib', 'capivasertib', 'everolimus',
      'gilteritinib', 'midostaurin',
      'sotorasib', 'adagrasib',
      'selpercatinib', 'pralsetinib',
      'larotrectinib', 'entrectinib',
      'sunitinib', 'sorafenib', 'lenvatinib', 'regorafenib', 'cabozantinib',
      'ivosidenib', 'pemigatinib', 'capmatinib', 'tepotinib', 'cetuximab', 'panitumumab', 'fulvestrant'
    ];
    const textLower = reportText.toLowerCase();
    const found = new Set<string>();
    DRUGS.forEach(drug => {
      if (textLower.includes(drug)) {
        found.add(drug.charAt(0).toUpperCase() + drug.slice(1));
      }
    });
    return Array.from(found);
  };

  const getEscatTier = (reportText: string, backendTier: string) => {
    if (backendTier && backendTier !== 'N/A' && backendTier !== 'N/D' && backendTier !== 'non determinato') {
      return backendTier;
    }
    const match = reportText.match(/ESCAT(?:\s*(?:Tier|Livello|Level)?:?\s*)?([IVX]+(?:-[A-C])?)/i);
    if (match) {
      let tier = match[1].toUpperCase();
      if (!tier.includes('-') && tier.length > 1 && ['A', 'B', 'C'].includes(tier[tier.length - 1])) {
        tier = tier.slice(0, -1) + '-' + tier[tier.length - 1];
      }
      return tier;
    }
    return 'N/D';
  };

  const getComplexityColor = (comp: string) => {
    switch (comp.toLowerCase()) {
      case 'low': return 'success';
      case 'moderate': return 'warning';
      case 'high': return 'error';
      default: return 'default';
    }
  };

  const getEscatColor = (tier: string) => {
    if (tier.includes('I-A') || tier.includes('I-B')) return 'success';
    if (tier.includes('II')) return 'info';
    return 'default';
  };

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

  const handleCompare = async (req: MTBRequest, conditionsToCompare: string[]) => {
    setCompareMode(true);
    setSelectedConditions(conditionsToCompare);
    setError(null);
    setReportData(null);
    setZeroShotData(null);
    setJudgeData(null);
    setLastRequest(req);

    const newResults = { vanilla: null, websearch: null, rag_testuale: null, full_graphrag: null };
    const newLoadings = { vanilla: false, websearch: false, rag_testuale: false, full_graphrag: false };
    const newErrors = { vanilla: null, websearch: null, rag_testuale: null, full_graphrag: null };

    conditionsToCompare.forEach(cond => {
      newLoadings[cond] = true;
    });

    setCompareResults(newResults);
    setCompareLoadings(newLoadings);
    setCompareErrors(newErrors);

    const endpoints: Record<string, string> = {
      vanilla: 'zeroshot',
      websearch: 'websearch',
      rag_testuale: 'rag',
      full_graphrag: 'analyze'
    };

    const fetchCondition = async (cond: string) => {
      try {
        const endpoint = endpoints[cond];
        const res = await fetch(`http://localhost:8000/api/v1/${endpoint}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(req)
        });
        if (!res.ok) throw new Error(`Errore HTTP ${res.status}`);
        const data: ReportResponse = await res.json();
        
        setCompareResults(prev => ({
          ...prev,
          [cond]: data
        }));
      } catch (err: any) {
        setCompareErrors(prev => ({
          ...prev,
          [cond]: err.message || `Errore nella generazione ${cond}`
        }));
      } finally {
        setCompareLoadings(prev => ({
          ...prev,
          [cond]: false
        }));
      }
    };

    Promise.all(conditionsToCompare.map(cond => fetchCondition(cond)));
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
              disabled={loading || isCompareLoading} 
            />
          </Grid>
          
          <Grid size={{ xs: 12, md: 8, lg: 9 }}>
            {error && (
              <Alert severity="error" sx={{ mb: 3 }}>
                {error}
              </Alert>
            )}

            {compareMode ? (
              (() => {
                const conditionMeta: Record<string, { title: string; color: string }> = {
                  vanilla: { title: 'Baseline Zero-Shot (Vanilla)', color: '#64748B' },
                  websearch: { title: 'WebSearch (Ablation)', color: '#0EA5E9' },
                  rag_testuale: { title: 'RAG Testuale (Ablation)', color: '#D97706' },
                  full_graphrag: { title: 'Full GraphRAG (Structured)', color: '#8B5CF6' }
                };
                
                return (
                  <Grid container spacing={3}>
                    {selectedConditions.map((cond) => {
                      const meta = conditionMeta[cond] || { title: cond, color: '#000000' };
                      const data = compareResults[cond];
                      const isLoading = compareLoadings[cond];
                      const colError = compareErrors[cond];
                      const gridMd = selectedConditions.length >= 4 ? 3 : (selectedConditions.length === 3 ? 4 : 6);
                      
                      return (
                        <Grid size={{ xs: 12, md: gridMd }} key={cond}>
                          <Typography variant="h6" sx={{ fontWeight: 700, mb: 2, color: meta.color }}>
                            {meta.title}
                          </Typography>
                          
                          {isLoading && (
                            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 15, border: '1px dashed #CBD5E1', borderRadius: 2, bgcolor: 'background.paper' }}>
                              <CircularProgress size={40} thickness={4} sx={{ color: meta.color }} />
                              <Typography variant="body2" sx={{ mt: 2, color: 'text.secondary', fontWeight: 500 }}>
                                Generazione report in corso...
                              </Typography>
                            </Box>
                          )}
                          
                          {colError && (
                            <Alert severity="error" sx={{ mb: 2 }}>
                              {colError}
                            </Alert>
                          )}
                          
                          {data && !isLoading && (
                            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                              {/* HIGHLIGHTS CARD */}
                              <Card variant="outlined" sx={{ bgcolor: '#F8FAFC', borderLeft: `4px solid ${meta.color}`, overflow: 'visible' }}>
                                <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1, color: '#475569', fontSize: '0.75rem', letterSpacing: '0.05em' }}>
                                    ELEMENTI CHIAVE CONFRONTO
                                  </Typography>
                                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                      <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>ESCAT Tier:</Typography>
                                      <Chip 
                                        label={getEscatTier(data.report, data.escat_tier)} 
                                        size="small" 
                                        sx={{ 
                                          fontWeight: 700, 
                                          bgcolor: getEscatTier(data.report, data.escat_tier) !== 'N/D' ? `${meta.color}15` : '#E2E8F0',
                                          color: getEscatTier(data.report, data.escat_tier) !== 'N/D' ? meta.color : 'text.secondary'
                                        }} 
                                      />
                                    </Box>
                                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                                      <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>Farmaci Raccomandati:</Typography>
                                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                                        {getExtractedDrugs(data.report, data.drug_candidates).length === 0 ? (
                                          <Typography variant="caption" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>Nessuno individuato</Typography>
                                        ) : (
                                          getExtractedDrugs(data.report, data.drug_candidates).map((d, i) => (
                                            <Chip key={i} label={d} size="small" variant="outlined" sx={{ fontSize: '0.7rem', fontWeight: 500, borderColor: `${meta.color}40`, color: meta.color }} />
                                          ))
                                        )}
                                      </Box>
                                    </Box>
                                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                                      <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>PMID Citati ({data.cited_pmids.length}):</Typography>
                                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                                        {data.cited_pmids.length === 0 ? (
                                          <Typography variant="caption" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>Nessuna citazione</Typography>
                                        ) : (
                                          data.cited_pmids.map((pmid, i) => (
                                            <Chip 
                                              key={i} 
                                              label={pmid} 
                                              size="small" 
                                              variant="outlined" 
                                              component="a" 
                                              href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}`} 
                                              target="_blank" 
                                              clickable 
                                              sx={{ fontSize: '0.7rem', height: 20 }} 
                                            />
                                          ))
                                        )}
                                      </Box>
                                    </Box>
                                  </Box>
                                </CardContent>
                              </Card>
                              
                              {/* REPORT VIEW */}
                              <ReportView 
                                data={data} 
                                onEnrich={cond === 'full_graphrag' ? handleEnrich : undefined} 
                                enriching={cond === 'full_graphrag' ? enriching : false} 
                              />
                              
                              {/* STRUCTURED DATA VIEW FOR EACH COLUMN */}
                              <StructuredData 
                                data={data} 
                                onEnrich={cond === 'full_graphrag' ? handleEnrich : undefined} 
                                enriching={cond === 'full_graphrag' ? enriching : false} 
                              />
                            </Box>
                          )}
                        </Grid>
                      );
                    })}
                  </Grid>
                );
              })()
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
