import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Stack,
  Divider,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import type { V3Query } from '../../types/v3Types';

interface V3QueryPanelProps {
  onExecuteQuery: (query: V3Query) => void;
  onSelectPreset: (presetKey: string) => void;
  activePresetKey?: string;
  loading?: boolean;
}

export const V3QueryPanel: React.FC<V3QueryPanelProps> = ({
  onExecuteQuery,
  onSelectPreset,
  activePresetKey,
  loading = false,
}) => {
  const [domain, setDomain] = useState<string>('therapeutic');
  const [biomarker, setBiomarker] = useState<string>('EGFR L858R');
  const [disease, setDisease] = useState<string>('Non-Small Cell Lung Cancer');
  const [intervention, setIntervention] = useState<string>('Osimertinib');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onExecuteQuery({
      query_id: `q_${Date.now()}`,
      claim_domain: domain,
      biomarker,
      disease,
      interventions: intervention ? [intervention] : [],
    });
  };

  const handlePresetClick = (key: string, presetDomain: string, presetBio: string, presetDis: string, presetInt: string) => {
    setDomain(presetDomain);
    setBiomarker(presetBio);
    setDisease(presetDis);
    setIntervention(presetInt);
    onSelectPreset(key);
  };

  return (
    <Card variant="outlined" sx={{ borderRadius: 2, borderColor: '#E2E8F0', bgcolor: '#FFFFFF', boxShadow: '0 1px 3px rgba(0,0,0,0.03)' }}>
      <CardContent sx={{ p: 2.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0F172A', fontSize: '0.95rem', mb: 1.5 }}>
          Query Evidence V3
        </Typography>

        {/* PRESET SELECTOR */}
        <Typography variant="caption" sx={{ fontWeight: 600, color: '#64748B', display: 'block', mb: 1 }}>
          Preset per il Relatore:
        </Typography>
        <Stack direction="column" spacing={0.75} sx={{ mb: 2 }}>
          <Button
            size="small"
            variant={activePresetKey === 'egfr_nsclc' ? 'contained' : 'outlined'}
            color="primary"
            onClick={() => handlePresetClick('egfr_nsclc', 'therapeutic', 'EGFR L858R', 'Non-Small Cell Lung Cancer', 'Osimertinib')}
            sx={{ justifyContent: 'flex-start', textTransform: 'none', fontSize: '0.78rem', py: 0.5, px: 1.25 }}
          >
            1. EGFR L858R / NSCLC (In indicazione)
          </Button>

          <Button
            size="small"
            variant={activePresetKey === 'egfr_melanoma' ? 'contained' : 'outlined'}
            color="primary"
            onClick={() => handlePresetClick('egfr_melanoma', 'therapeutic', 'EGFR L858R', 'Melanoma', 'Osimertinib')}
            sx={{ justifyContent: 'flex-start', textTransform: 'none', fontSize: '0.78rem', py: 0.5, px: 1.25 }}
          >
            2. EGFR L858R / Melanoma (Off-label)
          </Button>

          <Button
            size="small"
            variant={activePresetKey === 'alk_conjunctive' ? 'contained' : 'outlined'}
            color="primary"
            onClick={() => handlePresetClick('alk_conjunctive', 'therapeutic', 'EML4::ALK Fusion AND ALK G1202R', 'Non-Small Cell Lung Cancer', 'Lorlatinib')}
            sx={{ justifyContent: 'flex-start', textTransform: 'none', fontSize: '0.78rem', py: 0.5, px: 1.25 }}
          >
            3. ALK Fusion + G1202R (Booleano)
          </Button>

          <Button
            size="small"
            variant={activePresetKey === 'combo_melanoma' ? 'contained' : 'outlined'}
            color="primary"
            onClick={() => handlePresetClick('combo_melanoma', 'therapeutic', 'BRAF V600E', 'Melanoma', 'Dabrafenib + Trametinib')}
            sx={{ justifyContent: 'flex-start', textTransform: 'none', fontSize: '0.78rem', py: 0.5, px: 1.25 }}
          >
            4. Dabrafenib + Trametinib (Combo)
          </Button>
        </Stack>

        <Divider sx={{ my: 1.5 }} />

        {/* INPUT FORM */}
        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <FormControl fullWidth size="small">
            <InputLabel id="domain-label">Dominio Clinico</InputLabel>
            <Select
              labelId="domain-label"
              value={domain}
              label="Dominio Clinico"
              onChange={(e) => setDomain(e.target.value)}
            >
              <MenuItem value="therapeutic">Terapeutico (Therapeutic)</MenuItem>
              <MenuItem value="diagnostic">Diagnostico (Diagnostic)</MenuItem>
              <MenuItem value="prognostic">Prognostico (Prognostic)</MenuItem>
              <MenuItem value="untyped">Generico (Untyped)</MenuItem>
            </Select>
          </FormControl>

          <TextField
            label="Biomarcatore"
            size="small"
            fullWidth
            value={biomarker}
            onChange={(e) => setBiomarker(e.target.value)}
            required
          />

          <TextField
            label="Patologia"
            size="small"
            fullWidth
            value={disease}
            onChange={(e) => setDisease(e.target.value)}
            required
          />

          <TextField
            label="Intervento / Farmaco"
            size="small"
            fullWidth
            value={intervention}
            onChange={(e) => setIntervention(e.target.value)}
          />

          <Button
            type="submit"
            variant="contained"
            color="primary"
            startIcon={<SearchIcon />}
            disabled={loading}
            fullWidth
            sx={{ mt: 0.5, py: 0.75, fontWeight: 600, textTransform: 'none' }}
          >
            {loading ? 'Esecuzione...' : 'Esegui Query V3'}
          </Button>
        </Box>
      </CardContent>
    </Card>
  );
};

export default V3QueryPanel;
