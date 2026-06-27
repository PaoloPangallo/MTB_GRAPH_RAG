import { useState } from 'react';
import { 
  Card, 
  CardContent, 
  CardHeader, 
  TextField, 
  Select, 
  MenuItem, 
  InputLabel, 
  FormControl, 
  Button,
  Box,
  Typography,
  Switch,
  FormControlLabel,
  Checkbox,
  FormGroup
} from '@mui/material';
import type { MTBRequest, AlterationType } from '../types';

interface InputFormProps {
  onSubmit: (req: MTBRequest, isZeroShot: boolean) => void;
  onCompare: (req: MTBRequest, conditions: string[]) => void;
  disabled: boolean;
}

export default function InputForm({ onSubmit, onCompare, disabled }: InputFormProps) {
  const [gene, setGene] = useState('EGFR');
  const [variant, setVariant] = useState('L858R');
  const [tumorType, setTumorType] = useState('Lung Adenocarcinoma');
  const [alterationType, setAlterationType] = useState<AlterationType>('point_mutation');
  const [therapyLine, setTherapyLine] = useState('first-line');
  const [driverVariant, setDriverVariant] = useState('');
  const [enrichOncoKB, setEnrichOncoKB] = useState(false);
  const [compareConditions, setCompareConditions] = useState<string[]>(['vanilla', 'full_graphrag']);

  const handleToggleCondition = (cond: string) => {
    setCompareConditions(prev => {
      if (prev.includes(cond)) {
        return prev.filter(c => c !== cond);
      } else {
        return [...prev, cond];
      }
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      gene,
      variant,
      tumor_type: tumorType,
      alteration_type: alterationType,
      therapy_line: therapyLine,
      enrich_with_oncokb: enrichOncoKB,
      driver_variant: driverVariant || undefined
    }, false);
  };

  const handleZeroShotSubmit = () => {
    onSubmit({
      gene,
      variant,
      tumor_type: tumorType,
      alteration_type: alterationType,
      therapy_line: therapyLine,
      enrich_with_oncokb: false, // Zero-shot non usa OncoKB
      driver_variant: driverVariant || undefined
    }, true);
  };

  const handleCompareSubmit = () => {
    if (compareConditions.length < 2) return;
    onCompare({
      gene,
      variant,
      tumor_type: tumorType,
      alteration_type: alterationType,
      therapy_line: therapyLine,
      enrich_with_oncokb: enrichOncoKB,
      driver_variant: driverVariant || undefined
    }, compareConditions);
  };


  return (
    <Card variant="outlined">
      <CardHeader 
        title="Input Clinico" 
        titleTypographyProps={{ variant: 'h6', fontWeight: 600 }}
        sx={{ borderBottom: '1px solid #E2E8F0', bgcolor: 'background.default' }}
      />
      <CardContent>
        <form onSubmit={handleSubmit}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
            
            <TextField
              label="Gene (Opzionale per Biomarker)"
              value={gene}
              onChange={(e) => setGene(e.target.value)}
              fullWidth
              size="small"
              disabled={disabled}
            />

            <TextField
              label="Variante (es. L858R, TMB-High)"
              value={variant}
              onChange={(e) => {
                const val = e.target.value;
                setVariant(val);
                const valUpper = val.toUpperCase();
                if (valUpper.includes('MSI') || valUpper.includes('TMB')) {
                  setAlterationType('biomarker');
                }
              }}
              required
              fullWidth
              size="small"
              disabled={disabled}
            />

            <TextField
              label="Tipo Tumore (es. Lung Adenocarcinoma)"
              value={tumorType}
              onChange={(e) => setTumorType(e.target.value)}
              required
              fullWidth
              size="small"
              disabled={disabled}
            />

            <TextField
              label="Variante Driver Originale (Opzionale)"
              value={driverVariant}
              onChange={(e) => setDriverVariant(e.target.value)}
              fullWidth
              size="small"
              disabled={disabled}
              helperText="Variante driver di origine se questa è una resistenza acquisita (es. L858R per T790M)"
            />

            <FormControl fullWidth size="small" disabled={disabled}>
              <InputLabel>Tipo Alterazione</InputLabel>
              <Select
                value={alterationType}
                label="Tipo Alterazione"
                onChange={(e) => setAlterationType(e.target.value as AlterationType)}
              >
                <MenuItem value="point_mutation">Point Mutation</MenuItem>
                <MenuItem value="fusion">Fusion</MenuItem>
                <MenuItem value="cna">Copy Number Alteration (CNA)</MenuItem>
                <MenuItem value="itd">Internal Tandem Duplication (ITD)</MenuItem>
                <MenuItem value="atypical">Atypical / Exon</MenuItem>
                <MenuItem value="biomarker">Biomarker (MSI/TMB)</MenuItem>
              </Select>
            </FormControl>

            <FormControl fullWidth size="small" disabled={disabled}>
              <InputLabel>Linea Terapeutica</InputLabel>
              <Select
                value={therapyLine}
                label="Linea Terapeutica"
                onChange={(e) => setTherapyLine(e.target.value)}
              >
                <MenuItem value="first-line">First Line</MenuItem>
                <MenuItem value="second-line">Second Line</MenuItem>
                <MenuItem value="later-line">Later Line</MenuItem>
              </Select>
            </FormControl>

            <FormControlLabel
              control={
                <Switch 
                  checked={enrichOncoKB} 
                  onChange={(e) => setEnrichOncoKB(e.target.checked)} 
                  disabled={disabled}
                  color="primary"
                />
              }
              label={
                <Typography variant="body2" sx={{ fontWeight: 500 }}>
                  Integrazione OncoKB API Live
                </Typography>
              }
              sx={{ mt: 1, mb: 1, ml: 1 }}
            />

            <Button 
              type="submit" 
              variant="contained" 
              size="large" 
              color="primary"
              disabled={disabled}
              sx={{ mt: 2 }}
              disableElevation
            >
              Genera Report GraphRAG
            </Button>

            <Button 
              type="button" 
              variant="outlined" 
              color="secondary"
              size="medium" 
              disabled={disabled}
              onClick={handleZeroShotSubmit}
              disableElevation
            >
              Genera Baseline Zero-Shot
            </Button>

            <Box sx={{ mt: 1, p: 2, border: '1px solid #E2E8F0', borderRadius: 2, bgcolor: '#F8FAFC' }}>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1, color: 'text.primary' }}>
                Condizioni da confrontare:
              </Typography>
              <FormGroup>
                {[
                  { id: 'vanilla', label: 'Vanilla (Zero-Shot)' },
                  { id: 'websearch', label: 'WebSearch' },
                  { id: 'rag_testuale', label: 'RAG Testuale' },
                  { id: 'full_graphrag', label: 'Full GraphRAG' }
                ].map((item) => (
                  <FormControlLabel
                    key={item.id}
                    control={
                      <Checkbox
                        size="small"
                        checked={compareConditions.includes(item.id)}
                        onChange={() => handleToggleCondition(item.id)}
                        disabled={disabled}
                      />
                    }
                    label={
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {item.label}
                      </Typography>
                    }
                    sx={{ my: -0.5 }}
                  />
                ))}
              </FormGroup>
              {compareConditions.length < 2 && (
                <Typography variant="caption" color="error" sx={{ mt: 0.5, display: 'block' }}>
                  Seleziona almeno 2 condizioni.
                </Typography>
              )}
            </Box>

            <Button 
              type="button" 
              variant="contained" 
              color="info"
              size="medium" 
              disabled={disabled || compareConditions.length < 2}
              onClick={handleCompareSubmit}
              disableElevation
            >
              Confronto Side-by-Side
            </Button>
            
            <Typography variant="caption" color="text.secondary" align="center">
              L'analisi può richiedere fino a 30-40 secondi a causa dell'esecuzione locale del LLM.
            </Typography>

          </Box>
        </form>
      </CardContent>
    </Card>
  );
}
