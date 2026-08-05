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
  Chip,
  Button,
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '@mui/material';
import LocalHospitalIcon from '@mui/icons-material/LocalHospital';
import GavelIcon from '@mui/icons-material/Gavel';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import InputForm from './components/InputForm';
import ReportView from './components/ReportView';
import StructuredData from './components/StructuredData';
import JudgePanel from './components/JudgePanel';
import ArchitectureComparison from './components/ArchitectureComparison';
import V3EvidenceView from './components/V3EvidenceView';
import V3RunForm from './components/V3RunForm';
import ResearchConsole from './research/ResearchConsole';
import type { MTBRequest, ReportResponse, JudgeResponse, V3Request, V3RetrieveResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function App() {
  const [researchView, setResearchView] = useState(false);
  const [architectureView, setArchitectureView] = useState(false);
  const [loading, setLoading] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [isZeroShotMode, setIsZeroShotMode] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportData, setReportData] = useState<ReportResponse | null>(null);
  const [v3Data, setV3Data] = useState<V3RetrieveResponse | null>(null);
  const [v3Loading, setV3Loading] = useState(false);
  const [, setZeroShotData] = useState<ReportResponse | null>(null);
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
  const [expandedDetails, setExpandedDetails] = useState<Record<string, boolean>>({});

  const isCompareLoading = Object.values(compareLoadings).some(Boolean);

  const toggleDetails = (cond: string) => {
    setExpandedDetails(prev => ({ ...prev, [cond]: !prev[cond] }));
  };

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

  const handleV3Run = async (payload: V3Request) => {
    setV3Loading(true);
    setError(null);
    try {
      const response = await fetch(API_BASE_URL + '/api/v1/v3/retrieve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error('Errore V3 HTTP ' + response.status);
      setV3Data(await response.json() as V3RetrieveResponse);
    } catch (err: any) {
      setError(err.message || 'Errore durante il recupero V3');
    } finally {
      setV3Loading(false);
    }
  };

  const handleV3Retrieve = async (req: MTBRequest) => {
    setV3Loading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/v3/retrieve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query_id: 'ui-v3-retrieve',
          claim_domain: 'therapeutic',
          gene: req.gene || '',
          alteration: req.variant,
          disease: req.tumor_type,
          interventions: [],
          direction: req.mtb_goal === 'resistance' ? 'resistance' : '',
          policy_mode: 'strict_verified',
          include_warning: true,
          include_audit: true,
          include_rejected: true,
          result_limit: 50,
        }),
      });
      if (!response.ok) throw new Error(`Errore V3 HTTP ${response.status}`);
      setV3Data(await response.json() as V3RetrieveResponse);
    } catch (err: any) {
      setError(err.message || 'Errore durante il recupero V3');
    } finally {
      setV3Loading(false);
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
    const newLoadings: Record<string, boolean> = { vanilla: false, websearch: false, rag_testuale: false, full_graphrag: false };
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

  const conditionMeta: Record<string, { title: string; color: string; shortLabel: string }> = {
    vanilla: { title: 'Baseline Zero-Shot (Vanilla)', color: '#64748B', shortLabel: 'Vanilla' },
    websearch: { title: 'WebSearch (Ablation)', color: '#0EA5E9', shortLabel: 'WebSearch' },
    rag_testuale: { title: 'RAG Testuale (Ablation)', color: '#D97706', shortLabel: 'RAG Testuale' },
    full_graphrag: { title: 'Full GraphRAG (Structured)', color: '#8B5CF6', shortLabel: 'Full GraphRAG' }
  };

  // La console di ricerca sostituisce l'intera schermata: la pipeline
  // verificabile e' il centro dell'interfaccia, non un pannello fra altri.
  // Le viste precedenti restano raggiungibili finche' la migrazione non e'
  // completa (Fase H).
  if (researchView) {
    return (
      <Box sx={{ minHeight: '100vh' }}>
        <Box sx={{ position: 'fixed', top: 8, right: 12, zIndex: 1200 }}>
          <Button
            size="small"
            onClick={() => setResearchView(false)}
            sx={{ textTransform: 'none', color: '#93939f', fontSize: 12 }}
          >
            Torna alle viste precedenti
          </Button>
        </Box>
        <ResearchConsole />
      </Box>
    );
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <AppBar position="static">
        <Toolbar>
          <LocalHospitalIcon sx={{ mr: 2 }} />
          <Box>
            <Typography variant="h6" component="div" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              MTB GraphRAG Assistant
            </Typography>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.75)', letterSpacing: '0.03em' }}>
              Sistema di supporto alle decisioni oncologiche
            </Typography>
          </Box>
          <Button
            color="inherit"
            variant="outlined"
            onClick={() => setResearchView(true)}
            sx={{ ml: 'auto', mr: 1, borderColor: 'rgba(255,255,255,0.7)' }}
          >
            Pipeline verificabile
          </Button>
          <Button
            color="inherit"
            variant={architectureView ? 'outlined' : 'text'}
            startIcon={<CompareArrowsIcon />}
            onClick={() => setArchitectureView(current => !current)}
            sx={{ borderColor: architectureView ? 'rgba(255,255,255,0.7)' : undefined }}
          >
            {architectureView ? 'Torna al report' : 'Confronta architetture'}
          </Button>
        </Toolbar>
      </AppBar>

      {architectureView ? <ArchitectureComparison /> : <Container maxWidth="xl" sx={{ flexGrow: 1, py: 4 }}>
        <Grid container spacing={4}>
          <Grid size={{ xs: 12, md: 4, lg: 3 }}>
            <Card variant='outlined' sx={{ mb: 2, borderTop: '3px solid #176B5B' }}>
              <CardContent>
                <V3RunForm
                  onSubmit={handleV3Run}
                  disabled={loading || isCompareLoading || v3Loading}
                />
              </CardContent>
            </Card>
            <Typography variant='caption' color='text.secondary' sx={{ display: 'block', mb: 1 }}>
              Form legacy GraphRAG e confronto architetture
            </Typography>
            <InputForm
              onSubmit={handleAnalyze}
              onCompare={handleCompare}
              onV3Retrieve={handleV3Retrieve}
              disabled={loading || isCompareLoading || v3Loading}
            />
          </Grid>

          <Grid size={{ xs: 12, md: 8, lg: 9 }}>
            {error && (
              <Alert severity="error" sx={{ mb: 3 }}>
                {error}
              </Alert>
            )}

            {v3Loading && (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                <CircularProgress size={32} />
              </Box>
            )}
            {v3Data && !v3Loading && <Box sx={{ mb: 3 }}><V3EvidenceView data={v3Data} /></Box>}

            {compareMode ? (
              (() => {
                const completedConditions = selectedConditions.filter(
                  cond => compareResults[cond] !== null && !compareLoadings[cond]
                );
                const hasAnySummary = completedConditions.length > 0;
                // Fixed column width so each report is always readable
                const COL_WIDTH = 480;

                return (
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {/* SUMMARY BANNER SINOTTICO */}
                    {hasAnySummary && (
                      <Card variant="outlined" sx={{ borderTop: '3px solid #1E40AF' }}>
                        <Box sx={{
                          px: 2.5, py: 1.5,
                          borderBottom: '1px solid #E2E8F0',
                          background: 'linear-gradient(to right, #EFF6FF, #FFFFFF)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1.5,
                        }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 700, color: 'primary.dark' }}>
                            Confronto Sinottico
                          </Typography>
                          <Chip
                            label={`${completedConditions.length} / ${selectedConditions.length} condizioni`}
                            size="small"
                            variant="outlined"
                            sx={{ fontSize: '0.7rem' }}
                          />
                        </Box>
                        <Box sx={{ overflowX: 'auto' }}>
                          <Table size="small">
                            <TableBody>
                              <TableRow sx={{ bgcolor: '#F8FAFC' }}>
                                <TableCell sx={{ fontWeight: 700, fontSize: '0.72rem', color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.06em', width: 110, borderRight: '1px solid #E2E8F0' }}>
                                  Metrica
                                </TableCell>
                                {selectedConditions.map(cond => {
                                  const meta = conditionMeta[cond] || { title: cond, color: '#000', shortLabel: cond };
                                  return (
                                    <TableCell key={cond} align="center" sx={{ fontWeight: 700, fontSize: '0.75rem', color: meta.color, borderBottom: `2px solid ${meta.color}` }}>
                                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.75 }}>
                                        <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: meta.color, flexShrink: 0 }} />
                                        {meta.shortLabel}
                                      </Box>
                                    </TableCell>
                                  );
                                })}
                              </TableRow>
                              <TableRow>
                                <TableCell sx={{ fontWeight: 600, fontSize: '0.8rem', color: 'text.secondary', borderRight: '1px solid #E2E8F0' }}>ESCAT Tier</TableCell>
                                {selectedConditions.map(cond => {
                                  const data = compareResults[cond];
                                  const isLoading = compareLoadings[cond];
                                  return (
                                    <TableCell key={cond} align="center">
                                      {isLoading ? <CircularProgress size={14} /> : data ? (
                                        <Chip label={getEscatTier(data.report, data.escat_tier)} size="small" color={getEscatColor(getEscatTier(data.report, data.escat_tier)) as any} sx={{ fontWeight: 700, fontSize: '0.7rem' }} />
                                      ) : '—'}
                                    </TableCell>
                                  );
                                })}
                              </TableRow>
                              <TableRow sx={{ bgcolor: '#F8FAFC' }}>
                                <TableCell sx={{ fontWeight: 600, fontSize: '0.8rem', color: 'text.secondary', borderRight: '1px solid #E2E8F0' }}>Farmaci</TableCell>
                                {selectedConditions.map(cond => {
                                  const data = compareResults[cond];
                                  const isLoading = compareLoadings[cond];
                                  return (
                                    <TableCell key={cond} align="center">
                                      {isLoading ? <CircularProgress size={14} /> : data ? (
                                        <Typography variant="body2" sx={{ fontWeight: 700 }}>{getExtractedDrugs(data.report, data.drug_candidates).length}</Typography>
                                      ) : '—'}
                                    </TableCell>
                                  );
                                })}
                              </TableRow>
                              <TableRow>
                                <TableCell sx={{ fontWeight: 600, fontSize: '0.8rem', color: 'text.secondary', borderRight: '1px solid #E2E8F0' }}>PMID Citati</TableCell>
                                {selectedConditions.map(cond => {
                                  const data = compareResults[cond];
                                  const isLoading = compareLoadings[cond];
                                  return (
                                    <TableCell key={cond} align="center">
                                      {isLoading ? <CircularProgress size={14} /> : data ? (
                                        <Typography variant="body2" sx={{ fontWeight: 700 }}>{data.cited_pmids.length}</Typography>
                                      ) : '—'}
                                    </TableCell>
                                  );
                                })}
                              </TableRow>
                              <TableRow sx={{ bgcolor: '#F8FAFC' }}>
                                <TableCell sx={{ fontWeight: 600, fontSize: '0.8rem', color: 'text.secondary', borderRight: '1px solid #E2E8F0' }}>Complexity</TableCell>
                                {selectedConditions.map(cond => {
                                  const data = compareResults[cond];
                                  const isLoading = compareLoadings[cond];
                                  return (
                                    <TableCell key={cond} align="center">
                                      {isLoading ? <CircularProgress size={14} /> : data ? (
                                        <Chip label={data.complexity.toUpperCase()} size="small" color={getComplexityColor(data.complexity) as any} variant="outlined" sx={{ fontWeight: 700, fontSize: '0.68rem' }} />
                                      ) : '—'}
                                    </TableCell>
                                  );
                                })}
                              </TableRow>
                            </TableBody>
                          </Table>
                        </Box>
                      </Card>
                    )}

                    {/* COLONNE CON SCROLL ORIZZONTALE */}
                    <Box sx={{ overflowX: 'auto', pb: 1 }}>
                      <Box sx={{ display: 'flex', gap: 3, minWidth: 'max-content', alignItems: 'flex-start' }}>
                        {selectedConditions.map((cond) => {
                          const meta = conditionMeta[cond] || { title: cond, color: '#000000', shortLabel: cond };
                          const data = compareResults[cond];
                          const isLoading = compareLoadings[cond];
                          const colError = compareErrors[cond];

                          return (
                            <Box key={cond} sx={{ width: COL_WIDTH, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                              {/* Condition Header */}
                              <Box sx={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 1,
                                pb: 1,
                                borderBottom: `3px solid ${meta.color}`,
                              }}>
                                <Box sx={{ width: 12, height: 12, borderRadius: '50%', bgcolor: meta.color, flexShrink: 0, boxShadow: `0 0 6px ${meta.color}80` }} />
                                <Typography variant="subtitle1" sx={{ fontWeight: 700, color: meta.color }}>
                                  {meta.title}
                                </Typography>
                              </Box>

                              {isLoading && (
                                <Box sx={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  alignItems: 'center',
                                  py: 14,
                                  border: '1px dashed #CBD5E1',
                                  borderRadius: 2,
                                  bgcolor: '#FAFBFC',
                                  boxShadow: 'inset 0 2px 6px rgba(0,0,0,0.03)',
                                }}>
                                  <CircularProgress size={40} thickness={4} sx={{ color: meta.color }} />
                                  <Typography variant="body2" sx={{ mt: 2, color: 'text.secondary', fontWeight: 600 }}>
                                    Generazione in corso…
                                  </Typography>
                                  <Typography variant="caption" sx={{ mt: 0.5, color: '#94A3B8' }}>
                                    {meta.shortLabel}
                                  </Typography>
                                </Box>
                              )}

                              {colError && (
                                <Alert severity="error">{colError}</Alert>
                              )}

                              {data && !isLoading && (
                                <>
                                  {/* HIGHLIGHTS CARD */}
                                  <Card variant="outlined" sx={{ bgcolor: '#F8FAFC', borderTop: `3px solid ${meta.color}`, overflow: 'visible' }}>
                                    <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                                      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5, color: '#475569', fontSize: '0.68rem', letterSpacing: '0.07em', textTransform: 'uppercase' }}>
                                        Elementi Chiave
                                      </Typography>
                                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25 }}>
                                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                          <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>ESCAT Tier:</Typography>
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
                                          <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>Farmaci Raccomandati:</Typography>
                                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                                            {getExtractedDrugs(data.report, data.drug_candidates).length === 0 ? (
                                              <Typography variant="caption" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>Nessuno individuato</Typography>
                                            ) : (
                                              getExtractedDrugs(data.report, data.drug_candidates).map((d, i) => (
                                                <Chip key={i} label={d} size="small" variant="outlined" sx={{ fontSize: '0.67rem', fontWeight: 500, borderColor: `${meta.color}40`, color: meta.color }} />
                                              ))
                                            )}
                                          </Box>
                                        </Box>
                                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                                          <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>PMID Citati ({data.cited_pmids.length}):</Typography>
                                          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                                            {data.cited_pmids.length === 0 ? (
                                              <Typography variant="caption" sx={{ color: 'text.secondary', fontStyle: 'italic' }}>Nessuna citazione</Typography>
                                            ) : (
                                              data.cited_pmids.map((pmid, i) => (
                                                <Chip key={i} label={pmid} size="small" variant="outlined" component="a" href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}`} target="_blank" clickable sx={{ fontSize: '0.67rem', height: 20 }} />
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

                                  {/* STRUCTURED DATA — collassato di default in compare mode */}
                                  <Button
                                    size="small"
                                    variant="outlined"
                                    onClick={() => toggleDetails(cond)}
                                    endIcon={expandedDetails[cond] ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                    sx={{
                                      color: meta.color,
                                      borderColor: `${meta.color}60`,
                                      fontSize: '0.75rem',
                                      fontWeight: 600,
                                      '&:hover': { borderColor: meta.color, bgcolor: `${meta.color}08` }
                                    }}
                                  >
                                    {expandedDetails[cond] ? 'Nascondi dettagli (Graph, Tabelle)' : 'Mostra dettagli (Graph, Tabelle)'}
                                  </Button>

                                  {expandedDetails[cond] && (
                                    <StructuredData
                                      data={data}
                                      onEnrich={cond === 'full_graphrag' ? handleEnrich : undefined}
                                      enriching={cond === 'full_graphrag' ? enriching : false}
                                    />
                                  )}
                                </>
                              )}
                            </Box>
                          );
                        })}
                      </Box>
                    </Box>
                  </Box>
                );
              })()
            ) : loading ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 10 }}>
                <CircularProgress size={60} thickness={4} color={isZeroShotMode ? 'secondary' : 'primary'} />
                <Typography variant="h6" sx={{ mt: 3, color: 'text.secondary', fontWeight: 600 }}>
                  {isZeroShotMode ? 'Generazione report Zero-Shot…' : 'Elaborazione pipeline agentica GraphRAG…'}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', mt: 1, maxWidth: 480, textAlign: 'center' }}>
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
                <StructuredData data={reportData} onEnrich={handleEnrich} enriching={enriching} />
                {judgeData ? (
                  <JudgePanel judgeData={judgeData} />
                ) : (
                  <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                    <Button
                      variant="outlined"
                      color="primary"
                      onClick={handleJudge}
                      startIcon={<GavelIcon />}
                      sx={{ px: 3 }}
                    >
                      Richiedi valutazione indipendente LLM-as-judge
                    </Button>
                  </Box>
                )}
              </Box>
            ) : (
              <Box sx={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px dashed #CBD5E1',
                borderRadius: 3,
                bgcolor: 'background.paper',
                p: 6,
                gap: 2,
              }}>
                <LocalHospitalIcon sx={{ fontSize: 72, color: '#CBD5E1' }} />
                <Typography variant="h4" color="text.secondary" align="center" sx={{ fontWeight: 300 }}>
                  Inserisci i dati clinici nel modulo a sinistra per generare un report MTB.
                </Typography>
                <Typography variant="body1" color="text.secondary" align="center" sx={{ maxWidth: 420 }}>
                  Supporta modalità single-case, baseline zero-shot e confronto ablativo multi-condizione.
                </Typography>
              </Box>
            )}
          </Grid>
        </Grid>
      </Container>}
    </Box>
  );
}

export default App;
