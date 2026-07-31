import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Chip,
  Button,
  Stack,
  Collapse,
  Divider,
  Grid,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import type { V3ClaimResult } from '../../types/v3Types';

interface V3ClaimCardProps {
  claim: V3ClaimResult;
  onOpenProvenance: (claim: V3ClaimResult) => void;
  onOpenGateTrace: (claim: V3ClaimResult) => void;
}

export const V3ClaimCard: React.FC<V3ClaimCardProps> = ({
  claim,
  onOpenProvenance,
  onOpenGateTrace,
}) => {
  const [showQualifiers, setShowQualifiers] = useState(false);
  const [showSources, setShowSources] = useState(false);

  const getBucketChip = (b: string) => {
    switch (b) {
      case 'primary': return { label: 'PRIMARY', color: 'success' as const };
      case 'warning': return { label: 'WARNING', color: 'warning' as const };
      case 'audit': return { label: 'AUDIT', color: 'secondary' as const };
      case 'rejected': return { label: 'REJECTED', color: 'error' as const };
      default: return { label: b.toUpperCase(), color: 'default' as const };
    }
  };

  const bucketInfo = getBucketChip(claim.bucket);

  const prov = (claim.provenance || {}) as Record<string, any>;
  const pmidList = Array.isArray(prov.locators)
    ? prov.locators.map((l: any) => l.pmid || l.locator_value).filter(Boolean)
    : (prov.source_ids || []);

  const scoreObj = (claim.score || {}) as Record<string, any>;
  const formattedScore = typeof scoreObj.total_score === 'number'
    ? scoreObj.total_score
    : (typeof claim.score === 'number' ? claim.score : 0);

  return (
    <Card
      variant="outlined"
      sx={{
        mb: 2,
        borderRadius: 2,
        borderColor: '#E2E8F0',
        bgcolor: '#FFFFFF',
        boxShadow: '0 1px 2px rgba(0,0,0,0.02)',
        '&:hover': {
          borderColor: '#CBD5E1',
          boxShadow: '0 2px 6px rgba(0,0,0,0.04)',
        },
      }}
    >
      <CardContent sx={{ p: 2.25, '&:last-child': { pb: 2.25 } }}>
        {/* ROW 1: HEADER INFO & BUCKET BADGE */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 700, fontFamily: 'monospace', color: '#334155', fontSize: '0.82rem' }}>
              {claim.claim_id}
            </Typography>
            <Chip
              label={bucketInfo.label}
              size="small"
              color={bucketInfo.color}
              sx={{ fontWeight: 700, fontSize: '0.68rem', height: 22 }}
            />
            <Chip
              label={claim.claim_type}
              size="small"
              variant="outlined"
              sx={{ fontSize: '0.68rem', height: 22, color: '#64748B', borderColor: '#E2E8F0' }}
            />
          </Box>

          <Typography variant="caption" sx={{ fontWeight: 700, color: '#0F172A', fontFamily: 'monospace', fontSize: '0.8rem' }}>
            Score: {formattedScore.toFixed(3)}
          </Typography>
        </Box>

        {/* ROW 2: STRUCTURED CLINICAL TRIPLET */}
        <Grid container spacing={1.5} sx={{ my: 0.5, p: 1.5, bgcolor: '#F8FAFC', borderRadius: 1.5, border: '1px solid #F1F5F9' }}>
          <Grid size={{ xs: 12, md: 4 }}>
            <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, display: 'block', textTransform: 'uppercase', fontSize: '0.67rem' }}>
              Subject / Biomarker
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '0.88rem', mt: 0.25 }}>
              {claim.biomarker}
            </Typography>
          </Grid>

          <Grid size={{ xs: 12, md: 4 }}>
            <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, display: 'block', textTransform: 'uppercase', fontSize: '0.67rem' }}>
              Object / Intervention
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#1E40AF', fontSize: '0.88rem', mt: 0.25 }}>
              {claim.canonical_intervention}
            </Typography>
          </Grid>

          <Grid size={{ xs: 12, md: 4 }}>
            <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 600, display: 'block', textTransform: 'uppercase', fontSize: '0.67rem' }}>
              Disease Scope
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '0.88rem', mt: 0.25 }}>
              {claim.disease_scope}
            </Typography>
          </Grid>
        </Grid>

        {/* ROW 3: REASON CODES */}
        <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', my: 1.25 }}>
          {claim.reason_codes.map((rc, idx) => (
            <Chip
              key={idx}
              label={rc}
              size="small"
              sx={{ fontSize: '0.66rem', height: 20, bgcolor: '#F1F5F9', color: '#475569', fontWeight: 500 }}
            />
          ))}
          {claim.warnings.map((w, idx) => (
            <Chip
              key={idx}
              label={w}
              size="small"
              color="warning"
              variant="outlined"
              sx={{ fontSize: '0.66rem', height: 20, fontWeight: 500 }}
            />
          ))}
        </Box>

        <Divider sx={{ my: 1.25 }} />

        {/* ROW 4: ACTION LINKS */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
            <Button
              size="small"
              variant="text"
              color="primary"
              onClick={() => onOpenGateTrace(claim)}
              sx={{ fontSize: '0.75rem', textTransform: 'none', fontWeight: 600, px: 0.75, minWidth: 'auto' }}
            >
              Gate Trace
            </Button>

            <Button
              size="small"
              variant="text"
              color="secondary"
              onClick={() => onOpenProvenance(claim)}
              sx={{ fontSize: '0.75rem', textTransform: 'none', fontWeight: 600, px: 0.75, minWidth: 'auto' }}
            >
              Provenance
            </Button>

            <Button
              size="small"
              variant="text"
              color="inherit"
              onClick={() => setShowQualifiers(!showQualifiers)}
              endIcon={showQualifiers ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              sx={{ fontSize: '0.75rem', textTransform: 'none', color: '#64748B', px: 0.75, minWidth: 'auto' }}
            >
              Qualificatori
            </Button>

            <Button
              size="small"
              variant="text"
              color="inherit"
              onClick={() => setShowSources(!showSources)}
              endIcon={showSources ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              sx={{ fontSize: '0.75rem', textTransform: 'none', color: '#64748B', px: 0.75, minWidth: 'auto' }}
            >
              Fonti PMID ({pmidList.length})
            </Button>
          </Stack>
        </Box>

        {/* COLLAPSIBLE QUALIFIERS */}
        <Collapse in={showQualifiers} timeout="auto" unmountOnExit>
          <Box sx={{ mt: 1.5, p: 1.5, bgcolor: '#F8FAFC', borderRadius: 1.5, border: '1px solid #E2E8F0' }}>
            <Grid container spacing={2}>
              <Grid size={{ xs: 6, md: 3 }}>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block' }}>Applicability:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                  {prov.disease_relation_provenance?.relation_verified ? 'Verified Compatible' : 'Filtered'}
                </Typography>
              </Grid>
              <Grid size={{ xs: 6, md: 3 }}>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block' }}>Separability:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                  {claim.intervention_members && claim.intervention_members.length > 1 ? 'Combination' : 'Single Agent'}
                </Typography>
              </Grid>
              <Grid size={{ xs: 6, md: 3 }}>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block' }}>Evidence Level:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                  {claim.reason_codes.includes('PRECLINICAL_MODEL_WARNING') ? 'In Vitro / Preclinical' : 'Clinical Trial'}
                </Typography>
              </Grid>
              <Grid size={{ xs: 6, md: 3 }}>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block' }}>Qualification:</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>
                  {claim.bucket === 'primary' ? 'Final Evaluable' : 'Hard Filterable'}
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </Collapse>

        {/* COLLAPSIBLE SOURCES */}
        <Collapse in={showSources} timeout="auto" unmountOnExit>
          <Box sx={{ mt: 1.5, p: 1.5, bgcolor: '#F8FAFC', borderRadius: 1.5, border: '1px solid #E2E8F0' }}>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              {pmidList.length === 0 ? (
                <Typography variant="caption" sx={{ fontStyle: 'italic', color: '#94A3B8' }}>Nessun PMID registrato</Typography>
              ) : (
                pmidList.map((pmid: unknown, i: number) => {
                  const pmidClean = String(pmid).replace('PMID:', '');
                  return (
                    <Chip
                      key={i}
                      icon={<OpenInNewIcon fontSize="small" />}
                      label={`PMID: ${pmidClean}`}
                      component="a"
                      href={`https://pubmed.ncbi.nlm.nih.gov/${pmidClean}`}
                      target="_blank"
                      clickable
                      size="small"
                      variant="outlined"
                      sx={{ fontSize: '0.72rem', height: 24 }}
                    />
                  );
                })
              )}
            </Box>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
};

export default V3ClaimCard;
