import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import {
  Box,
  Paper,
  Typography,
  Chip,
  Divider,
  TextField,
  InputAdornment,
  IconButton,
  Switch,
  FormControlLabel,
  Slider,
  Button,
  Alert,
  Tooltip,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import CenterFocusStrongIcon from '@mui/icons-material/CenterFocusStrong';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import type { ReportResponse, GraphNode, GraphLink, SubGraphData } from '../types';

// ── Color palette per tipi di nodo ──────────────────────────

const NODE_COLORS: Record<string, string> = {
  gene:                  '#0EA5E9',
  variant:               '#8B5CF6',
  molecular_profile:     '#1E3A8A',
  drug:                  '#10B981',
  evidence:              '#F59E0B',
  publication:           '#D97706',
  clinical_trial:        '#7C3AED',
  companion_diagnostic:  '#06B6D4',
  resistance:            '#EF4444',
  llm_memory:            '#A21CAF',
};

const NODE_LABELS: Record<string, string> = {
  gene:                  'Gene',
  variant:               'Variante',
  molecular_profile:     'Profilo Molecolare',
  drug:                  'Farmaco',
  evidence:              'Evidenza',
  publication:           'Pubblicazione',
  clinical_trial:        'Trial Clinico',
  companion_diagnostic:  'Companion Diagnostic',
  resistance:            'Resistenza',
  llm_memory:            'Memoria LLM',
};

// ── Helper: genera grafo locale se l'API non è disponibile ──

function buildLocalGraph(data: ReportResponse): SubGraphData {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];

  const isZeroShot = data.complexity === 'zero-shot' || data.complexity === 'vanilla' || data.complexity === 'websearch' || data.complexity === 'rag_testuale';
  if (isZeroShot) {
    const isWebSearch = data.complexity === 'websearch';
    const isRAG = data.complexity === 'rag_testuale';
    
    let description = 'Memoria interna del Large Language Model. Nessun database consultato.';
    let label = 'LLM Parametric Memory';
    if (isWebSearch) {
      label = 'LLM + PubMed WebSearch';
      description = 'Generazione LLM arricchita da ricerca articoli PubMed inline.';
    } else if (isRAG) {
      label = 'LLM + Textual RAG';
      description = 'Generazione LLM arricchita da retrieval semantico di chunk di testo dal KG.';
    }

    nodes.push({
      id: 'llm_core', label: label, type: 'llm_memory',
      color: NODE_COLORS.llm_memory, val: 14,
      metadata: { description: description },
    });
    data.cited_pmids.forEach((pmid, idx) => {
      const pid = `halluc_pmid_${idx}`;
      nodes.push({
        id: pid, label: `PMID: ${pmid}`, type: 'publication',
        color: (isWebSearch || isRAG) ? '#F59E0B' : '#EF4444', // Orange for websearch/rag, red for zero-shot
        val: 5,
        metadata: {
          pmid, hallucinated: !isWebSearch && !isRAG,
          description: isWebSearch 
            ? 'PMID citato e recuperato via PubMed WebSearch.' 
            : (isRAG ? 'PMID citato ed estratto da RAG testuale.' : 'PMID citato dall\'LLM ma NON verificato. Probabile allucinazione.'),
          url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}`,
        },
      });
      links.push({ source: 'llm_core', target: pid, label: 'CITED', type: 'CITED' });
    });
    return { nodes, links };
  }

  // ── GraphRAG: costruisci da dati strutturati ──
  const geneSymbol = data.report.match(/Gene:\s*([A-Za-z0-9]+)/)?.[1] || 'GENE';
  const gid = `gene_${geneSymbol}`;
  nodes.push({
    id: gid, label: geneSymbol, type: 'gene',
    color: NODE_COLORS.gene, val: 12,
    metadata: { hugo_symbol: geneSymbol },
  });

  const mpId = `mp_${data.escat_tier || 'profile'}`;
  nodes.push({
    id: mpId, label: `ESCAT: ${data.escat_tier || 'N/D'}`, type: 'molecular_profile',
    color: NODE_COLORS.molecular_profile, val: 14,
    metadata: { escat_tier: data.escat_tier },
  });
  links.push({ source: gid, target: mpId, label: 'HAS_VARIANT', type: 'HAS_VARIANT' });

  data.drug_candidates.forEach((drug, idx) => {
    const did = `drug_${idx}_${drug.drug_name}`;
    nodes.push({
      id: did, label: drug.drug_name, type: 'drug',
      color: NODE_COLORS.drug, val: 8,
      metadata: {
        drug_name: drug.drug_name,
        approved: drug.approved,
        companion_diagnostic: drug.companion_diagnostic,
        evidence_level: drug.evidence_level,
      },
    });
    links.push({ source: mpId, target: did, label: 'TARGETS_DRUG', type: 'TARGETS_DRUG' });
  });

  data.resistance_data.forEach((res, idx) => {
    const rid = `res_${idx}_${res.variant}`;
    nodes.push({
      id: rid, label: res.variant, type: 'resistance',
      color: NODE_COLORS.resistance, val: 8,
      metadata: {
        variant_name: res.variant,
        evidence_level: res.evidence_level,
        disease: res.disease,
        statement: res.statement,
      },
    });
    links.push({ source: gid, target: rid, label: 'RESISTANCE', type: 'RESISTANCE' });
  });

  data.trial_candidates.forEach((trial, idx) => {
    const tid = `trial_${idx}_${trial.nct_id}`;
    nodes.push({
      id: tid, label: trial.nct_id, type: 'clinical_trial',
      color: NODE_COLORS.clinical_trial, val: 7,
      metadata: {
        nct_id: trial.nct_id,
        title: trial.title,
        phase: trial.phase,
        status: trial.status,
        url: `https://clinicaltrials.gov/ct2/show/${trial.nct_id}`,
      },
    });
    links.push({ source: gid, target: tid, label: 'CLINICAL_TRIAL', type: 'CLINICAL_TRIAL' });
  });

  data.cited_pmids.forEach((pmid, idx) => {
    const pid = `pmid_${idx}_${pmid}`;
    nodes.push({
      id: pid, label: `PMID: ${pmid}`, type: 'publication',
      color: NODE_COLORS.publication, val: 5,
      metadata: {
        pmid,
        url: `https://pubmed.ncbi.nlm.nih.gov/${pmid}`,
      },
    });
    links.push({ source: mpId, target: pid, label: 'CITED_IN', type: 'CITED_IN' });
  });

  return { nodes, links };
}


// ── Componente principale ───────────────────────────────────

interface KnowledgeGraph3DProps {
  data: ReportResponse;
}

export default function KnowledgeGraph3D({ data }: KnowledgeGraph3DProps) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [graphData, setGraphData] = useState<SubGraphData>({ nodes: [], links: [] });
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [is3D, setIs3D] = useState(true);
  const [chargeStrength, setChargeStrength] = useState(-120);
  const [visibleTypes, setVisibleTypes] = useState<Set<string>>(new Set(Object.keys(NODE_COLORS)));
  const [dimensions, setDimensions] = useState({ width: 800, height: 560 });

  // ── Resize observer ─────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        setDimensions({ width: Math.max(400, width), height: 560 });
      }
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  // ── Carica sotto-grafo dal backend o fallback locale ─────
  useEffect(() => {
    const isZeroShot = data.complexity === 'zero-shot' || data.complexity === 'vanilla' || data.complexity === 'websearch' || data.complexity === 'rag_testuale';
    const geneSymbol = data.report.match(/Gene:\s*([A-Za-z0-9]+)/)?.[1] || '';

    const fetchSubgraph = async () => {
      try {
        const params = new URLSearchParams();
        if (isZeroShot) {
          params.set('mode', 'zeroshot');
          params.set('cited_pmids', data.cited_pmids.join(','));
        } else {
          params.set('gene', geneSymbol);
          // Extract variant from report
          const variantMatch = data.report.match(/Variante?:\s*(?:[A-Za-z0-9]+\s+)?([A-Za-z0-9_\- ]+?)[\s.,(\n]/);
          params.set('variant', variantMatch?.[1]?.trim() || '');
          params.set('tumor_type', '');
          params.set('mode', 'graphrag');
        }
        const res = await fetch(`http://localhost:8000/api/v1/subgraph?${params.toString()}`);
        if (!res.ok) throw new Error('API error');
        const result: SubGraphData = await res.json();
        if (result.nodes.length > 0) {
          setGraphData(result);
          return;
        }
      } catch {
        // Fallback silenzioso al grafo locale
      }
      // Fallback: costruisci localmente
      setGraphData(buildLocalGraph(data));
    };

    fetchSubgraph();
  }, [data]);

  // ── Filtraggio nodi per visibilità e ricerca ─────────────
  const filteredData = useMemo(() => {
    const visNodes = graphData.nodes.filter(n => visibleTypes.has(n.type));
    const visIds = new Set(visNodes.map(n => n.id));
    const visLinks = graphData.links.filter(l => {
      const src = typeof l.source === 'string' ? l.source : (l.source as any).id;
      const tgt = typeof l.target === 'string' ? l.target : (l.target as any).id;
      return visIds.has(src) && visIds.has(tgt);
    });

    // Evidenzia nodi trovati dalla ricerca
    const q = searchQuery.toLowerCase().trim();
    const highlighted = q
      ? visNodes.map(n => ({
          ...n,
          color: n.label.toLowerCase().includes(q)
            ? '#FFFFFF'
            : NODE_COLORS[n.type] || n.color,
        }))
      : visNodes;

    return { nodes: highlighted, links: visLinks };
  }, [graphData, visibleTypes, searchQuery]);

  // ── Handlers ────────────────────────────────────────────
  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node as GraphNode);
    // Zoom-to-fit su click
    if (fgRef.current) {
      const distance = 120;
      const distRatio = 1 + distance / Math.hypot(node.x || 0, node.y || 0, node.z || 0);
      fgRef.current.cameraPosition(
        { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
        { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
        1000
      );
    }
    // Apri URL esterni al doppio click (gestito come singolo per UX mobile)
    const url = node.metadata?.url;
    if (url && (node.type === 'publication' || node.type === 'clinical_trial')) {
      // Non aprire automaticamente, l'utente userà il pulsante nel sidebar
    }
  }, []);

  const handleResetView = useCallback(() => {
    if (fgRef.current) {
      fgRef.current.cameraPosition({ x: 0, y: 0, z: 400 }, { x: 0, y: 0, z: 0 }, 1000);
    }
    setSelectedNode(null);
    setSearchQuery('');
  }, []);

  const handleSearchFocus = useCallback(() => {
    if (!searchQuery.trim() || !fgRef.current) return;
    const q = searchQuery.toLowerCase().trim();
    const node = graphData.nodes.find(n => n.label.toLowerCase().includes(q));
    if (node) {
      handleNodeClick(node);
    }
  }, [searchQuery, graphData.nodes, handleNodeClick]);

  const toggleType = useCallback((type: string) => {
    setVisibleTypes(prev => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const isZeroShot = data.complexity === 'zero-shot';

  // ── Conteggi per legenda ─────────────────────────────────
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const n of graphData.nodes) {
      counts[n.type] = (counts[n.type] || 0) + 1;
    }
    return counts;
  }, [graphData.nodes]);

  return (
    <Box sx={{ display: 'flex', gap: 0, height: 600, position: 'relative' }}>
      {/* ── Zero-Shot Warning Banner ─────────────────────── */}
      {isZeroShot && (
        <Alert
          severity="error"
          icon={<WarningAmberIcon />}
          sx={{
            position: 'absolute',
            top: 12,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
            maxWidth: 520,
            backdropFilter: 'blur(8px)',
            bgcolor: 'rgba(239,68,68,0.9)',
            color: '#FFF',
            fontWeight: 600,
            fontSize: '0.8rem',
            '& .MuiAlert-icon': { color: '#FFF' },
          }}
        >
          Zero-Shot: nessuna consultazione del Knowledge Graph. I PMID visualizzati sono allucinazioni dell'LLM.
        </Alert>
      )}

      {/* ── Pannello di controllo sovrapposto ─────────────── */}
      <Paper
        elevation={0}
        sx={{
          position: 'absolute',
          top: isZeroShot ? 64 : 12,
          left: 12,
          zIndex: 10,
          width: 220,
          p: 1.5,
          bgcolor: 'rgba(15,23,42,0.85)',
          backdropFilter: 'blur(12px)',
          borderRadius: 2,
          border: '1px solid rgba(148,163,184,0.2)',
          color: '#E2E8F0',
          maxHeight: 500,
          overflow: 'auto',
        }}
      >
        {/* Ricerca */}
        <TextField
          size="small"
          placeholder="Cerca nodo..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearchFocus()}
          fullWidth
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: '#94A3B8', fontSize: 18 }} />
                </InputAdornment>
              ),
              sx: {
                color: '#E2E8F0',
                fontSize: '0.8rem',
                bgcolor: 'rgba(30,41,59,0.6)',
                '& fieldset': { borderColor: 'rgba(148,163,184,0.3)' },
              },
            },
          }}
          sx={{ mb: 1.5 }}
        />

        {/* Controlli */}
        <Box sx={{ display: 'flex', gap: 1, mb: 1.5, justifyContent: 'space-between' }}>
          <Tooltip title="Reset vista camera">
            <IconButton size="small" onClick={handleResetView} sx={{ color: '#94A3B8' }}>
              <CenterFocusStrongIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={is3D}
                onChange={e => setIs3D(e.target.checked)}
                sx={{ '& .MuiSwitch-thumb': { bgcolor: '#0EA5E9' } }}
              />
            }
            label={<Typography variant="caption" sx={{ color: '#94A3B8' }}>3D</Typography>}
            sx={{ mr: 0 }}
          />
        </Box>

        {/* Forza repulsione */}
        <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mb: 0.5 }}>
          Espansione grafo
        </Typography>
        <Slider
          size="small"
          min={-400}
          max={-20}
          value={chargeStrength}
          onChange={(_, v) => setChargeStrength(v as number)}
          sx={{ color: '#0EA5E9', mb: 1.5 }}
        />

        <Divider sx={{ borderColor: 'rgba(148,163,184,0.15)', my: 1 }} />

        {/* Legenda interattiva */}
        <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, mb: 1, display: 'block' }}>
          Legenda ({graphData.nodes.length} nodi)
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
          {Object.entries(NODE_COLORS)
            .filter(([type]) => typeCounts[type])
            .map(([type, color]) => (
              <Chip
                key={type}
                label={`${NODE_LABELS[type] || type} (${typeCounts[type] || 0})`}
                size="small"
                onClick={() => toggleType(type)}
                sx={{
                  bgcolor: visibleTypes.has(type) ? color : 'rgba(100,116,139,0.3)',
                  color: '#FFF',
                  fontSize: '0.65rem',
                  fontWeight: 600,
                  height: 24,
                  opacity: visibleTypes.has(type) ? 1 : 0.4,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  '&:hover': { opacity: 1, transform: 'scale(1.05)' },
                }}
              />
            ))}
        </Box>
      </Paper>

      {/* ── Grafo 3D ─────────────────────────────────────── */}
      <Box
        ref={containerRef}
        sx={{
          flexGrow: 1,
          bgcolor: '#0A0F1E',
          borderRadius: 2,
          overflow: 'hidden',
          position: 'relative',
          background: 'radial-gradient(ellipse at center, #0F172A 0%, #020617 100%)',
        }}
      >
        <ForceGraph3D
          ref={fgRef}
          graphData={filteredData}
          width={selectedNode ? dimensions.width - 320 : dimensions.width}
          height={dimensions.height}
          backgroundColor="rgba(0,0,0,0)"
          nodeLabel={(node: any) => {
            const n = node as GraphNode;
            return `<div style="background:rgba(15,23,42,0.95);padding:8px 12px;border-radius:8px;border:1px solid ${n.color};font-family:Inter,sans-serif;font-size:12px;color:#E2E8F0;max-width:280px;">
              <div style="font-weight:700;color:${n.color};margin-bottom:4px;">${NODE_LABELS[n.type] || n.type}</div>
              <div style="font-weight:600;margin-bottom:2px;">${n.label}</div>
              ${n.metadata?.disease ? `<div style="color:#94A3B8;font-size:11px;">🏥 ${n.metadata.disease}</div>` : ''}
              ${n.metadata?.evidence_level ? `<div style="color:#94A3B8;font-size:11px;">📊 Level ${n.metadata.evidence_level}</div>` : ''}
              ${n.metadata?.hallucinated ? `<div style="color:#EF4444;font-size:11px;font-weight:600;">⚠️ Allucinato</div>` : ''}
              <div style="color:#64748B;font-size:10px;margin-top:4px;">Click per dettagli</div>
            </div>`;
          }}
          nodeColor={(node: any) => (node as GraphNode).color}
          nodeVal={(node: any) => (node as GraphNode).val || 6}
          nodeOpacity={0.92}
          nodeResolution={16}
          linkLabel={(link: any) => (link as GraphLink).label}
          linkColor={(link: any) => {
            const l = link as GraphLink;
            if (l.type === 'HALLUCINATED') return '#EF4444';
            if (l.type === 'RESISTANCE' || l.type === 'RESISTANCE_VARIANT' || l.type === 'RESISTS_DRUG') return '#F87171';
            return '#334155';
          }}
          linkWidth={(link: any) => (link as GraphLink).type === 'HALLUCINATED' ? 2 : 1}
          linkOpacity={0.6}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={(link: any) => (link as GraphLink).type === 'HALLUCINATED' ? 3 : 0}
          linkDirectionalParticleColor={() => '#EF4444'}
          linkDirectionalParticleSpeed={0.005}
          onNodeClick={handleNodeClick}
          onNodeDragEnd={(node: any) => {
            node.fx = node.x;
            node.fy = node.y;
            node.fz = node.z;
          }}
          numDimensions={is3D ? 3 : 2}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
          cooldownTicks={100}
          warmupTicks={50}
        />
      </Box>

      {/* ── Sidebar dettagli nodo ─────────────────────────── */}
      {selectedNode && (
        <Paper
          elevation={4}
          sx={{
            width: 310,
            flexShrink: 0,
            p: 2.5,
            bgcolor: '#0F172A',
            color: '#E2E8F0',
            borderLeft: `3px solid ${selectedNode.color}`,
            borderRadius: '0 8px 8px 0',
            overflow: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 1.5,
          }}
        >
          {/* Header */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{
              width: 14, height: 14, borderRadius: '50%',
              bgcolor: selectedNode.color,
              boxShadow: `0 0 10px ${selectedNode.color}80`,
              flexShrink: 0,
            }} />
            <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1 }}>
              {NODE_LABELS[selectedNode.type] || selectedNode.type}
            </Typography>
          </Box>

          <Typography variant="h6" sx={{ fontWeight: 700, color: '#F1F5F9', lineHeight: 1.2 }}>
            {selectedNode.label}
          </Typography>

          {selectedNode.metadata?.hallucinated && (
            <Alert severity="error" sx={{ py: 0.5, fontSize: '0.75rem' }}>
              Questo PMID è stato generato dall'LLM senza consultare alcun database.
              Con alta probabilità è un'allucinazione.
            </Alert>
          )}

          <Divider sx={{ borderColor: 'rgba(148,163,184,0.15)' }} />

          {/* Dettagli clinici */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {selectedNode.metadata?.evidence_level && (
              <DetailRow label="Livello Evidenza" value={selectedNode.metadata.evidence_level} />
            )}
            {selectedNode.metadata?.significance && (
              <DetailRow label="Significatività" value={selectedNode.metadata.significance} />
            )}
            {selectedNode.metadata?.disease && (
              <DetailRow label="Malattia" value={selectedNode.metadata.disease} />
            )}
            {selectedNode.metadata?.statement && (
              <DetailRow label="Statement" value={selectedNode.metadata.statement} multiline />
            )}
            {selectedNode.metadata?.drug_name && (
              <DetailRow label="Farmaco" value={selectedNode.metadata.drug_name} />
            )}
            {selectedNode.metadata?.approved !== undefined && (
              <DetailRow label="Approvato" value={selectedNode.metadata.approved ? 'Sì ✅' : 'No ❌'} />
            )}
            {selectedNode.metadata?.companion_diagnostic && (
              <DetailRow label="Companion Diagnostic" value={selectedNode.metadata.companion_diagnostic} />
            )}
            {selectedNode.metadata?.phase && (
              <DetailRow label="Fase Trial" value={selectedNode.metadata.phase} />
            )}
            {selectedNode.metadata?.status && (
              <DetailRow label="Stato" value={selectedNode.metadata.status} />
            )}
            {selectedNode.metadata?.title && (
              <DetailRow label="Titolo" value={selectedNode.metadata.title} multiline />
            )}
            {selectedNode.metadata?.citation_text && (
              <DetailRow label="Citazione" value={selectedNode.metadata.citation_text} multiline />
            )}
            {selectedNode.metadata?.pmid && (
              <DetailRow label="PMID" value={String(selectedNode.metadata.pmid)} />
            )}
            {selectedNode.metadata?.hugo_symbol && (
              <DetailRow label="HUGO Symbol" value={selectedNode.metadata.hugo_symbol} />
            )}
            {selectedNode.metadata?.escat_tier && (
              <DetailRow label="ESCAT Tier" value={selectedNode.metadata.escat_tier} />
            )}
            {selectedNode.metadata?.description && (
              <DetailRow label="Descrizione" value={selectedNode.metadata.description} multiline />
            )}
          </Box>

          {/* Azioni */}
          {selectedNode.metadata?.url && (
            <>
              <Divider sx={{ borderColor: 'rgba(148,163,184,0.15)' }} />
              <Button
                variant="outlined"
                size="small"
                startIcon={<OpenInNewIcon />}
                onClick={() => window.open(selectedNode.metadata.url, '_blank')}
                sx={{
                  color: selectedNode.color,
                  borderColor: selectedNode.color,
                  fontSize: '0.75rem',
                  '&:hover': { bgcolor: `${selectedNode.color}20` },
                }}
              >
                {selectedNode.type === 'publication' ? 'Apri PubMed' : 'Apri ClinicalTrials.gov'}
              </Button>
            </>
          )}

          {/* Chiudi */}
          <Button
            size="small"
            onClick={() => setSelectedNode(null)}
            sx={{ color: '#64748B', fontSize: '0.7rem', mt: 'auto' }}
          >
            Chiudi pannello
          </Button>
        </Paper>
      )}
    </Box>
  );
}


// ── Sub-component: riga di dettaglio ────────────────────────

function DetailRow({ label, value, multiline }: { label: string; value: string; multiline?: boolean }) {
  return (
    <Box>
      <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </Typography>
      <Typography
        variant="body2"
        sx={{
          color: '#CBD5E1',
          fontSize: '0.8rem',
          lineHeight: 1.4,
          ...(multiline ? { whiteSpace: 'pre-wrap', wordBreak: 'break-word' } : {}),
        }}
      >
        {value}
      </Typography>
    </Box>
  );
}
