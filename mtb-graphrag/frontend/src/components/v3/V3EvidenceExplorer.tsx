import React, { useState, useEffect, useCallback } from 'react';
import { Box, Grid, Alert, CircularProgress, Typography, Card, Button } from '@mui/material';

import V3QueryPanel from './V3QueryPanel';
import V3SummaryHeader from './V3SummaryHeader';
import V3BucketTabs from './V3BucketTabs';
import V3ClaimCard from './V3ClaimCard';
import V3GateTraceView from './V3GateTraceView';
import V3ProvenanceDrawer from './V3ProvenanceDrawer';
import V3ReportPanel from './V3ReportPanel';

import { getV3Metadata, retrieveV3Evidence, renderV3Report } from '../../api/v3Api';
import type {
  V3ClaimResult,
  EvidenceBucket,
  V3Query,
  V3RetrievalResponse,
  V3MetadataResponse,
} from '../../types/v3Types';

export const V3EvidenceExplorer: React.FC = () => {
  const [activeBucket, setActiveBucket] = useState<EvidenceBucket>('primary');
  const [metadata, setMetadata] = useState<V3MetadataResponse | null>(null);
  const [result, setResult] = useState<V3RetrievalResponse | null>(null);

  const [selectedClaimForGate, setSelectedClaimForGate] = useState<V3ClaimResult | null>(null);
  const [selectedClaimForProv, setSelectedClaimForProv] = useState<V3ClaimResult | null>(null);

  const [loading, setLoading] = useState<boolean>(false);
  const [rendering, setRendering] = useState<boolean>(false);
  const [renderedReportText, setRenderedReportText] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  // Caricamento metadati d'avvio dal backend reale
  useEffect(() => {
    let isMounted = true;
    getV3Metadata()
      .then((meta) => {
        if (isMounted) setMetadata(meta);
      })
      .catch((err) => {
        if (isMounted) console.warn('Impossibile recuperare metadati V3 dal backend:', err.message);
      });
    return () => { isMounted = false; };
  }, []);

  // Esecuzione query reale V3 sul backend
  const handleExecuteQuery = useCallback(async (query: V3Query) => {
    setLoading(true);
    setError(null);
    setRenderedReportText(undefined);

    try {
      const response = await retrieveV3Evidence({
        domain: query.claim_domain || 'therapeutic',
        biomarker: query.biomarker,
        disease: query.disease,
        intervention: query.interventions && query.interventions.length > 0 ? query.interventions[0] : null,
        policy_mode: query.policy_mode || 'strict_verified',
        result_limit: query.result_limit,
      });

      setResult(response);
    } catch (err: any) {
      setError(err instanceof Error ? err.message : 'Errore durante la chiamata al backend V3');
    } finally {
      setLoading(false);
    }
  }, []);

  // Inizializzazione automatica al primo montaggio con la query reale EGFR L858R / NSCLC
  useEffect(() => {
    handleExecuteQuery({
      claim_domain: 'therapeutic',
      biomarker: 'EGFR L858R',
      disease: 'Non-Small Cell Lung Cancer',
      interventions: ['Osimertinib'],
    });
  }, [handleExecuteQuery]);

  const handleSelectPreset = (presetKey: string) => {
    switch (presetKey) {
      case 'egfr_nsclc':
        handleExecuteQuery({
          claim_domain: 'therapeutic',
          biomarker: 'EGFR L858R',
          disease: 'Non-Small Cell Lung Cancer',
          interventions: ['Osimertinib'],
        });
        break;
      case 'egfr_melanoma':
        handleExecuteQuery({
          claim_domain: 'therapeutic',
          biomarker: 'EGFR L858R',
          disease: 'Melanoma',
          interventions: ['Osimertinib'],
        });
        break;
      case 'alk_conjunctive':
        handleExecuteQuery({
          claim_domain: 'therapeutic',
          biomarker: 'EML4::ALK Fusion AND ALK G1202R',
          disease: 'Non-Small Cell Lung Cancer',
          interventions: ['Lorlatinib'],
        });
        break;
      case 'combo_melanoma':
        handleExecuteQuery({
          claim_domain: 'therapeutic',
          biomarker: 'BRAF V600E',
          disease: 'Melanoma',
          interventions: ['Dabrafenib'],
        });
        break;
      default:
        break;
    }
  };

  // Rendering narrativo reale via backend
  const handleRenderNarrative = async () => {
    if (!result) return;
    const currentClaims = result.buckets[activeBucket] || [];
    if (currentClaims.length === 0) {
      setRenderedReportText('Nessuna claim presente nel bucket attivo per il rendering.');
      return;
    }

    setRendering(true);
    try {
      const renderRes = await renderV3Report({
        query_id: result.query_id,
        claims: currentClaims,
      });
      setRenderedReportText(renderRes.rendered_report);
    } catch (err: any) {
      setRenderedReportText(`Errore durante il rendering: ${err.message}`);
    } finally {
      setRendering(false);
    }
  };

  const activeClaims: V3ClaimResult[] = result?.buckets[activeBucket] || [];

  return (
    <Box sx={{ flexGrow: 1, py: 1 }}>
      <Grid container spacing={2.5}>
        {/* LEFT COLUMN: QUERY FORM PANEL */}
        <Grid size={{ xs: 12, lg: 3.5 }}>
          <V3QueryPanel
            onExecuteQuery={handleExecuteQuery}
            onSelectPreset={handleSelectPreset}
            loading={loading}
          />
        </Grid>

        {/* RIGHT COLUMN: MAIN EVIDENCE EXPLORER PANEL */}
        <Grid size={{ xs: 12, lg: 8.5 }}>
          {error && (
            <Alert severity="error" sx={{ mb: 2, borderRadius: 1.5 }}>
              {error}
            </Alert>
          )}

          {loading ? (
            <Card variant="outlined" sx={{ borderRadius: 2, borderColor: '#E2E8F0', p: 8, textAlign: 'center' }}>
              <CircularProgress size={36} thickness={4} color="primary" />
              <Typography variant="body2" sx={{ mt: 2, color: '#64748B', fontWeight: 600 }}>
                Interrogazione del retriever V3 sul corpus promosso reale...
              </Typography>
            </Card>
          ) : result ? (
            <>
              {/* SUMMARY HEADER */}
              <V3SummaryHeader result={result} metadata={metadata} />

              {/* BUCKET NAVIGATION TABS */}
              <V3BucketTabs
                activeBucket={activeBucket}
                onBucketChange={setActiveBucket}
                counts={result.summary}
              />

              {/* ACTION: GENERATE NARRATIVE RENDER */}
              <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600 }}>
                  Visualizzazione claim per il bucket: <strong style={{ textTransform: 'uppercase' }}>{activeBucket}</strong> ({activeClaims.length})
                </Typography>

                <Button
                  size="small"
                  variant="outlined"
                  color="primary"
                  onClick={handleRenderNarrative}
                  disabled={rendering || activeClaims.length === 0}
                  sx={{ textTransform: 'none', fontWeight: 600, fontSize: '0.78rem' }}
                >
                  {rendering ? 'Generazione...' : 'Genera rendering narrativo'}
                </Button>
              </Box>

              {/* CLAIMS LIST */}
              {activeClaims.length === 0 ? (
                <Card variant="outlined" sx={{ p: 4, textAlign: 'center', borderColor: '#E2E8F0', borderRadius: 2, bgcolor: '#FFFFFF' }}>
                  <Typography variant="body2" sx={{ color: '#64748B', fontStyle: 'italic' }}>
                    Nessuna claim presente nel bucket {activeBucket.toUpperCase()} per la query corrente.
                  </Typography>
                </Card>
              ) : (
                activeClaims.map((claim) => (
                  <V3ClaimCard
                    key={claim.claim_id}
                    claim={claim}
                    onOpenGateTrace={(c) => setSelectedClaimForGate(c)}
                    onOpenProvenance={(c) => setSelectedClaimForProv(c)}
                  />
                ))
              )}

              {/* OPTIONAL REPORT PANEL */}
              <V3ReportPanel reportText={renderedReportText} />
            </>
          ) : null}
        </Grid>
      </Grid>

      {/* GATE TRACE MODAL */}
      <V3GateTraceView
        open={Boolean(selectedClaimForGate)}
        onClose={() => setSelectedClaimForGate(null)}
        claim={selectedClaimForGate}
      />

      {/* PROVENANCE DRAWER */}
      <V3ProvenanceDrawer
        open={Boolean(selectedClaimForProv)}
        onClose={() => setSelectedClaimForProv(null)}
        claim={selectedClaimForProv}
      />
    </Box>
  );
};

export default V3EvidenceExplorer;
