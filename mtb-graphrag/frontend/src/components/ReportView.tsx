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
    <Card variant="outlined" sx={{ overflow: 'visible' }}>
      <Box sx={{ 
        p: 3, 
        borderBottom: '1px solid #E2E8F0', 
        bgcolor: 'background.default',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 2
      }}>
        <Typography variant="h5" color="primary.main" sx={{ fontWeight: 600 }}>
          Sintesi Clinica
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Chip 
            label={`Complexity: ${data.complexity.toUpperCase()}`} 
            color={getComplexityColor(data.complexity) as any}
            variant="outlined"
            sx={{ fontWeight: 600 }}
          />
          <Chip 
            label={`ESCAT Tier: ${data.escat_tier}`} 
            color={getEscatColor(data.escat_tier) as any}
            sx={{ fontWeight: 600 }}
          />
        </Box>
      </Box>

      <CardContent sx={{ p: 4 }}>
        <Box sx={{ 
          typography: 'body1', 
          '& p': { mb: 2 },
          '& h1, & h2, & h3': { color: 'primary.main', mt: 3, mb: 2, fontWeight: 600 },
          '& ul': { mb: 2, pl: 3 },
          '& li': { mb: 1 },
          '& strong': { fontWeight: 600 }
        }}>
          <ReactMarkdown
            components={{
              a: ({ node, ...props }) => (
                <a
                  {...props}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: '#2E7EBA', textDecoration: 'underline', fontWeight: 600 }}
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
