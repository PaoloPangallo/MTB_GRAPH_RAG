import { Box, Card, CardContent, Typography, Chip } from '@mui/material';
import ReactMarkdown from 'react-markdown';
import type { ReportResponse } from '../types';

interface ReportViewProps {
  data: ReportResponse;
  onEnrich?: () => void;
  enriching?: boolean;
}

export default function ReportView({ data }: ReportViewProps) {

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

  return (
    <Card
      variant="outlined"
      sx={{
        overflow: 'visible',
        borderTop: '3px solid',
        borderTopColor: 'primary.main',
      }}
    >
      <Box sx={{
        px: 3,
        py: 2,
        borderBottom: '1px solid #E2E8F0',
        background: 'linear-gradient(to right, #EFF6FF, #FFFFFF)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 2
      }}>
        <Typography variant="h5" color="primary.dark" sx={{ fontWeight: 700, letterSpacing: '-0.01em' }}>
          Sintesi Clinica
        </Typography>

        <Box sx={{ display: 'flex', gap: 1 }}>
          <Chip
            label={`Complexity: ${data.complexity.toUpperCase()}`}
            color={getComplexityColor(data.complexity) as any}
            variant="outlined"
            sx={{ fontWeight: 700, px: 0.5 }}
          />
          <Chip
            label={`ESCAT Tier: ${data.escat_tier}`}
            color={getEscatColor(data.escat_tier) as any}
            sx={{ fontWeight: 700, px: 0.5 }}
          />
        </Box>
      </Box>

      <CardContent sx={{ p: 4 }}>
        <Box sx={{
          typography: 'body1',
          '& p': { mb: 2, lineHeight: 1.75 },
          '& h1': {
            fontSize: '1.3rem',
            fontWeight: 700,
            color: 'primary.dark',
            mt: 3, mb: 1.5,
            pb: 1,
            borderBottom: '2px solid #DBEAFE'
          },
          '& h2': {
            fontSize: '1.15rem',
            fontWeight: 600,
            color: 'primary.main',
            mt: 3, mb: 1.5
          },
          '& h3': {
            fontSize: '1rem',
            fontWeight: 600,
            color: '#1E293B',
            mt: 2.5, mb: 1
          },
          '& ul': { mb: 2, pl: 3 },
          '& ol': { mb: 2, pl: 3 },
          '& li': { mb: 0.75, lineHeight: 1.7 },
          '& strong': { fontWeight: 700, color: '#0F172A' },
          '& em': { fontStyle: 'italic', color: '#475569' },
          '& blockquote': {
            borderLeft: '3px solid #0F766E',
            pl: 2,
            ml: 0,
            bgcolor: '#F0FDF4',
            py: 1,
            borderRadius: '0 6px 6px 0',
            fontStyle: 'italic',
            color: '#065F46',
          },
          '& code': {
            fontFamily: '"JetBrains Mono", "Fira Code", "Consolas", monospace',
            bgcolor: '#F1F5F9',
            color: '#334155',
            px: '4px',
            py: '1px',
            borderRadius: '3px',
            fontSize: '0.85em',
          },
          '& hr': {
            borderColor: '#E2E8F0',
            my: 3
          },
          '& a': {
            color: '#1E40AF',
            fontWeight: 600,
            textDecorationColor: '#BFDBFE',
            '&:hover': { textDecorationColor: '#1E40AF' }
          }
        }}>
          <ReactMarkdown
            components={{
              a: ({ node, ...props }) => (
                <a
                  {...props}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#1E40AF', textDecoration: 'underline', fontWeight: 600, textDecorationColor: '#BFDBFE' }}
                />
              )
            }}
          >
            {data.report}
          </ReactMarkdown>
        </Box>
      </CardContent>
    </Card>
  );
}
