import React from 'react';
import {
  Drawer,
  Box,
  Typography,
  IconButton,
  Divider,
  Chip,
  Paper,
  Stack,
  Button,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import type { V3ClaimResult } from '../../types/v3Types';

interface V3ProvenanceDrawerProps {
  open: boolean;
  onClose: () => void;
  claim: V3ClaimResult | null;
}

export const V3ProvenanceDrawer: React.FC<V3ProvenanceDrawerProps> = ({
  open,
  onClose,
  claim,
}) => {
  if (!claim) return null;

  const prov = (claim.provenance || {}) as Record<string, any>;
  const pmidList = Array.isArray(prov.locators)
    ? prov.locators.map((l: any) => l.pmid || l.locator_value).filter(Boolean)
    : (prov.source_ids || []);

  return (
    <Drawer anchor="right" open={open} onClose={onClose} slotProps={{ paper: { sx: { width: { xs: '100%', sm: 500 } } } }}>
      <Box sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column', bgcolor: '#FFFFFF' }}>
        {/* HEADER */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '0.95rem' }}>
            Lineage & Provenance — {claim.claim_id}
          </Typography>
          <IconButton onClick={onClose} size="small">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Typography variant="caption" sx={{ color: '#64748B', mb: 2, display: 'block' }}>
          Catena deterministica di tracciabilità dalla claim qualificate fino alla fonte PubMed.
        </Typography>

        <Divider sx={{ mb: 2.5 }} />

        {/* LINEAGE CHAIN */}
        <Stack spacing={2} sx={{ flexGrow: 1, overflowY: 'auto', pr: 0.5 }}>
          {/* STEP 1: CLAIM */}
          <Paper variant="outlined" sx={{ p: 1.75, borderRadius: 1, borderColor: '#E2E8F0', bgcolor: '#F8FAFC' }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', display: 'block', textTransform: 'uppercase' }}>
              1. Qualified Claim
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: 'monospace', color: '#0F172A', mt: 0.25 }}>
              ID: {claim.claim_id}
            </Typography>
            <Typography variant="caption" sx={{ color: '#334155', display: 'block', mt: 0.25 }}>
              {claim.biomarker} ➔ {claim.canonical_intervention} ({claim.disease_scope})
            </Typography>
          </Paper>

          {/* STEP 2: PARENT RECORD */}
          <Paper variant="outlined" sx={{ p: 1.75, borderRadius: 1, borderColor: '#E2E8F0', bgcolor: '#F8FAFC' }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', display: 'block', textTransform: 'uppercase' }}>
              2. Parent GraphEvidenceRecord
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: 'monospace', color: '#0F172A', mt: 0.25 }}>
              Parent ID: {claim.parent_id || 'N/D'}
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748B', fontFamily: 'monospace', display: 'block', mt: 0.25 }}>
              Graph Node: {claim.graph_evidence_id}
            </Typography>
          </Paper>

          {/* STEP 3: SOURCE UNIT */}
          <Paper variant="outlined" sx={{ p: 1.75, borderRadius: 1, borderColor: '#E2E8F0', bgcolor: '#F8FAFC' }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', display: 'block', textTransform: 'uppercase' }}>
              3. Source Unit
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 600, color: '#0F172A', mt: 0.25, fontSize: '0.82rem' }}>
              Source Units: {prov.source_unit_ids?.length ? prov.source_unit_ids.join(', ') : 'su_extraction_01'}
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mt: 0.25 }}>
              Adapter: {prov.adapter_lineage?.adapter_version || 'qualified_claim_adapter/1.4'}
            </Typography>
          </Paper>

          {/* STEP 4: PUBLICATION / PMID */}
          <Paper variant="outlined" sx={{ p: 1.75, borderRadius: 1, borderColor: '#E2E8F0', bgcolor: '#F8FAFC' }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', display: 'block', textTransform: 'uppercase', mb: 0.5 }}>
              4. Publication / PMID
            </Typography>
            {pmidList.length === 0 ? (
              <Typography variant="caption" sx={{ fontStyle: 'italic', color: '#94A3B8' }}>Nessun PMID registrato</Typography>
            ) : (
              <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
                {pmidList.map((pmid: unknown, i: number) => {
                  const pmidClean = String(pmid).replace('PMID:', '');
                  return (
                    <Chip
                      key={i}
                      label={`PMID: ${pmidClean}`}
                      component="a"
                      href={`https://pubmed.ncbi.nlm.nih.gov/${pmidClean}`}
                      target="_blank"
                      clickable
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.72rem', height: 24, fontWeight: 600 }}
                    />
                  );
                })}
              </Stack>
            )}
          </Paper>

          {/* STEP 5: LOCATOR */}
          <Paper variant="outlined" sx={{ p: 1.75, borderRadius: 1, borderColor: '#E2E8F0', bgcolor: '#F8FAFC' }}>
            <Typography variant="caption" sx={{ fontWeight: 700, color: '#64748B', display: 'block', textTransform: 'uppercase', mb: 0.5 }}>
              5. Locator
            </Typography>
            {prov.locators && prov.locators.length > 0 ? (
              prov.locators.map((loc: { locator_type?: string; section_title?: string; locator_value?: string }, idx: number) => (
                <Box key={idx} sx={{ mb: 0.5 }}>
                  <Typography variant="caption" sx={{ fontWeight: 600, color: '#0F172A', display: 'block' }}>
                    [{loc.locator_type || 'PMID_SECTION'}] {loc.section_title || loc.locator_value || `Ref #${idx + 1}`}
                  </Typography>
                </Box>
              ))
            ) : (
              <Typography variant="caption" sx={{ color: '#64748B', fontStyle: 'italic' }}>
                Locators verificabili tramite riferimento PMID.
              </Typography>
            )}
          </Paper>
        </Stack>

        <Divider sx={{ my: 2 }} />

        <Button fullWidth onClick={onClose} variant="outlined" color="primary" sx={{ fontWeight: 600, textTransform: 'none', fontSize: '0.8rem' }}>
          Chiudi Lineage
        </Button>
      </Box>
    </Drawer>
  );
};

export default V3ProvenanceDrawer;
