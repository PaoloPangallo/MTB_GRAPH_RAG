import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from '@mui/material';
import type { V3ClaimResult, GateTraceStep } from '../../types/v3Types';

interface V3GateTraceViewProps {
  open: boolean;
  onClose: () => void;
  claim: V3ClaimResult | null;
}

export const V3GateTraceView: React.FC<V3GateTraceViewProps> = ({
  open,
  onClose,
  claim,
}) => {
  if (!claim) return null;

  const gateTraceObj = (claim.gate_trace || {}) as Record<string, any>;
  const steps: GateTraceStep[] = Array.isArray(gateTraceObj.steps) ? gateTraceObj.steps : (Array.isArray(claim.gate_trace) ? (claim.gate_trace as any) : []);

  const getStatusChip = (status: string) => {
    switch (status) {
      case 'pass': return <Chip label="PASS" size="small" color="success" sx={{ fontWeight: 700, fontSize: '0.68rem', height: 20 }} />;
      case 'warning': return <Chip label="WARN" size="small" color="warning" sx={{ fontWeight: 700, fontSize: '0.68rem', height: 20 }} />;
      case 'fail': return <Chip label="FAIL" size="small" color="error" sx={{ fontWeight: 700, fontSize: '0.68rem', height: 20 }} />;
      default: return <Chip label="N/A" size="small" sx={{ fontWeight: 700, fontSize: '0.68rem', height: 20 }} />;
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ bgcolor: '#0F172A', color: '#FFFFFF', py: 1.75, px: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, fontSize: '1rem' }}>
              Traccia Verticale dei Gate — Claim ID: {claim.claim_id}
            </Typography>
            <Typography variant="caption" sx={{ color: '#94A3B8', fontFamily: 'monospace' }}>
              Dominant Gate: {gateTraceObj.dominant_gate || 'structural_gate'} | Gate Version: {gateTraceObj.gate_version || '1.3'}
            </Typography>
          </Box>
          <Chip
            label={`Bucket: ${claim.bucket.toUpperCase()}`}
            color={claim.bucket === 'primary' ? 'success' : claim.bucket === 'warning' ? 'warning' : claim.bucket === 'audit' ? 'secondary' : 'error'}
            sx={{ fontWeight: 700, fontSize: '0.75rem' }}
          />
        </Box>
      </DialogTitle>

      <DialogContent dividers sx={{ p: 2.5, bgcolor: '#F8FAFC' }}>
        <Typography variant="caption" sx={{ color: '#475569', display: 'block', mb: 2, fontWeight: 500 }}>
          Verifica deterministica su 10 stadi strutturali. I punteggi di ranking non possono sovrascrivere l'esito dei gate.
        </Typography>

        <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 1.5, borderColor: '#E2E8F0' }}>
          <Table size="small" aria-label="Gate Trace Table">
            <TableHead sx={{ bgcolor: '#F1F5F9' }}>
              <TableRow>
                <TableCell sx={{ fontWeight: 700, fontSize: '0.75rem', width: 40 }}>#</TableCell>
                <TableCell sx={{ fontWeight: 700, fontSize: '0.75rem', width: 180 }}>Stadio Pipeline</TableCell>
                <TableCell sx={{ fontWeight: 700, fontSize: '0.75rem', width: 70 }} align="center">Esito</TableCell>
                <TableCell sx={{ fontWeight: 700, fontSize: '0.75rem', width: 190 }}>Reason Code</TableCell>
                <TableCell sx={{ fontWeight: 700, fontSize: '0.75rem' }}>Valore Query vs Claim</TableCell>
                <TableCell sx={{ fontWeight: 700, fontSize: '0.75rem' }}>Motivazione / Spiegazione Clinica</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {steps.map((st, idx) => (
                <TableRow key={idx} sx={{ '&:nth-of-type(even)': { bgcolor: '#FAFAFA' } }}>
                  <TableCell sx={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748B' }}>{idx + 1}</TableCell>
                  <TableCell sx={{ fontSize: '0.78rem', fontWeight: 700, color: '#0F172A' }}>{st.stage_name}</TableCell>
                  <TableCell align="center">{getStatusChip(st.status)}</TableCell>
                  <TableCell sx={{ fontSize: '0.72rem', fontFamily: 'monospace', color: '#334155', fontWeight: 600 }}>{st.reason_code}</TableCell>
                  <TableCell sx={{ fontSize: '0.75rem' }}>
                    <Box sx={{ fontSize: '0.72rem', fontFamily: 'monospace' }}>
                      <span style={{ color: '#64748B' }}>Q:</span> <strong>{st.query_value}</strong>
                    </Box>
                    <Box sx={{ fontSize: '0.72rem', fontFamily: 'monospace' }}>
                      <span style={{ color: '#64748B' }}>C:</span> <strong style={{ color: '#1E40AF' }}>{st.claim_value}</strong>
                    </Box>
                  </TableCell>
                  <TableCell sx={{ fontSize: '0.75rem', color: '#334155' }}>{st.explanation}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 1.5, bgcolor: '#F1F5F9' }}>
        <Button onClick={onClose} variant="outlined" color="primary" sx={{ fontWeight: 600, textTransform: 'none', fontSize: '0.8rem' }}>
          Chiudi Traccia
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default V3GateTraceView;
