import React from 'react';
import { Tabs, Tab, Box, Typography } from '@mui/material';
import type { EvidenceBucket } from '../../types/v3Types';

interface V3BucketTabsProps {
  activeBucket: EvidenceBucket;
  onBucketChange: (bucket: EvidenceBucket) => void;
  counts: {
    primary: number;
    warning: number;
    audit: number;
    rejected: number;
  };
}

export const V3BucketTabs: React.FC<V3BucketTabsProps> = ({
  activeBucket,
  onBucketChange,
  counts,
}) => {
  const handleChange = (_: React.SyntheticEvent, newValue: EvidenceBucket) => {
    onBucketChange(newValue);
  };

  return (
    <Box sx={{ borderBottom: 1, borderColor: '#E2E8F0', mb: 2 }}>
      <Tabs
        value={activeBucket}
        onChange={handleChange}
        aria-label="V3 Evidence Bucket Tabs"
        sx={{
          minHeight: 36,
          '& .MuiTab-root': {
            fontWeight: 700,
            textTransform: 'none',
            fontSize: '0.85rem',
            minHeight: 36,
            py: 0.75,
            px: 2,
          },
        }}
      >
        <Tab value="primary" label={`Primary (${counts.primary})`} />
        <Tab value="warning" label={`Warning (${counts.warning})`} />
        <Tab value="audit" label={`Audit (${counts.audit})`} />
        <Tab value="rejected" label={`Rejected (${counts.rejected})`} />
      </Tabs>

      <Box sx={{ py: 1, px: 1.5, bgcolor: '#F8FAFC', borderRadius: 1, mt: 1, border: '1px solid #F1F5F9' }}>
        {activeBucket === 'primary' && (
          <Typography variant="caption" sx={{ color: '#166534', fontWeight: 600 }}>
            Bucket Primary: Evidenze verificate in indicazione canonica dal gate strutturale.
          </Typography>
        )}
        {activeBucket === 'warning' && (
          <Typography variant="caption" sx={{ color: '#92400E', fontWeight: 600 }}>
            Bucket Warning: Evidenze qualificate con riserva strutturale (es. regime combinato, derivati salini o modelli in vitro).
          </Typography>
        )}
        {activeBucket === 'audit' && (
          <Typography variant="caption" sx={{ color: '#6B21A8', fontWeight: 600 }}>
            Bucket Audit: Candidati esclusi dal rendering primario per mismatch di indicazione/patologia, consultabili per verificabilità.
          </Typography>
        )}
        {activeBucket === 'rejected' && (
          <Typography variant="caption" sx={{ color: '#991B1B', fontWeight: 600 }}>
            Bucket Rejected: Candidati scartati dal gate nativo per incompatibilità biologica o disgiunzione.
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default V3BucketTabs;
