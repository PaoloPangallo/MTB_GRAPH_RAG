import React from 'react';
import { Box, Card, CardContent, Typography, Alert, Divider } from '@mui/material';
import ReactMarkdown from 'react-markdown';

interface V3ReportPanelProps {
  reportText?: string;
}

export const V3ReportPanel: React.FC<V3ReportPanelProps> = ({ reportText }) => {
  if (!reportText) return null;

  return (
    <Card variant="outlined" sx={{ borderRadius: 2, borderColor: '#E2E8F0', mt: 2.5, bgcolor: '#FFFFFF', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
      <CardContent sx={{ p: 2.5 }}>
        {/* MANDATORY DISCLAIMER LABEL */}
        <Alert severity="info" variant="outlined" sx={{ mb: 2, fontWeight: 600, fontSize: '0.8rem', borderColor: '#CBD5E1', color: '#334155', bgcolor: '#F8FAFC' }}>
          Testo generato a partire dalle claim strutturate; non determina retrieval, bucket o ranking.
        </Alert>

        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '0.9rem', mb: 1 }}>
          Report Sintetico Opzionale (Sintesi Testuale)
        </Typography>

        <Divider sx={{ mb: 2 }} />

        <Box sx={{ p: 2, bgcolor: '#F8FAFC', borderRadius: 1.5, border: '1px solid #F1F5F9', color: '#1E293B', fontSize: '0.85rem', lineHeight: 1.6 }}>
          <ReactMarkdown>{reportText}</ReactMarkdown>
        </Box>
      </CardContent>
    </Card>
  );
};

export default V3ReportPanel;
