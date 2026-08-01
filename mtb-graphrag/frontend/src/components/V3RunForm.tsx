import { useState } from 'react';
import {
  Box,
  Button,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import type { V3Request } from '../types';

interface V3RunFormProps {
  disabled?: boolean;
  onSubmit: (payload: V3Request) => void;
}

const initialState = {
  gene: 'EGFR',
  alteration: 'L858R',
  biomarker: '',
  disease: 'Lung Adenocarcinoma',
  interventions: '',
  intervention_class: '',
  direction: '',
  policy_mode: 'strict_verified',
  result_limit: '20',
  alteration_type: 'point_mutation',
  intervention_combination: false,
};

export default function V3RunForm({ disabled = false, onSubmit }: V3RunFormProps) {
  const [form, setForm] = useState(initialState);
  const setField = (key: keyof typeof initialState, value: string | boolean) => {
    setForm(previous => ({ ...previous, [key]: value }));
  };

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const limit = Math.max(1, Math.min(500, Number(form.result_limit) || 20));
    onSubmit({
      query_id: 'ui-v3-retrieve',
      claim_domain: 'therapeutic',
      gene: form.gene.trim(),
      alteration: form.alteration.trim(),
      biomarker: form.biomarker.trim(),
      disease: form.disease.trim(),
      interventions: form.interventions.split(',').map(value => value.trim()).filter(Boolean),
      intervention_class: form.intervention_class.trim(),
      intervention_combination: form.intervention_combination,
      direction: form.direction,
      policy_mode: form.policy_mode,
      include_warning: true,
      include_audit: true,
      include_rejected: true,
      result_limit: limit,
    });
  };

  return (
    <Box component='form' onSubmit={submit}>
      <Typography variant='h6' sx={{ fontWeight: 800, mb: 1 }}>
        Caso clinico V3
      </Typography>
      <Typography variant='body2' color='text.secondary' sx={{ mb: 2 }}>
        Input esplicito della pipeline deterministica qualified-claim.
      </Typography>
      <Stack spacing={1.5}>
        <TextField label='Gene' value={form.gene} onChange={event => setField('gene', event.target.value)} fullWidth />
        <TextField label='Alterazione' value={form.alteration} onChange={event => setField('alteration', event.target.value)} fullWidth />
        <TextField label='Biomarcatore' value={form.biomarker} onChange={event => setField('biomarker', event.target.value)} helperText='Opzionale: usa la sintassi del repository quando disponibile.' fullWidth />
        <TextField label='Malattia' value={form.disease} onChange={event => setField('disease', event.target.value)} fullWidth />
        <TextField label='Interventi' value={form.interventions} onChange={event => setField('interventions', event.target.value)} helperText='Più interventi separati da virgola.' fullWidth />
        <TextField label='Tipo alterazione' value={form.alteration_type} onChange={event => setField('alteration_type', event.target.value)} select fullWidth>
          <MenuItem value='point_mutation'>Point mutation</MenuItem>
          <MenuItem value='fusion'>Fusion</MenuItem>
          <MenuItem value='cna'>CNA</MenuItem>
          <MenuItem value='biomarker'>Biomarker</MenuItem>
        </TextField>
        <TextField label='Classe intervento' value={form.intervention_class} onChange={event => setField('intervention_class', event.target.value)} helperText='Invio al backend solo se valorizzato.' fullWidth />
        <Box>
          <Typography component='label' htmlFor='v3-direction' variant='caption' sx={{ display: 'block', mb: 0.5 }}>Direzione</Typography>
          <select id='v3-direction' aria-label='Direzione' value={form.direction} onChange={event => setField('direction', event.target.value)} style={{ width: '100%', minHeight: 46, border: '1px solid #b6c5c0', borderRadius: 4, padding: '0 12px', background: '#fff', fontSize: 16 }}>
            <option value=''>Non vincolata</option>
            <option value='sensitivity'>Sensitivity</option>
            <option value='resistance'>Resistance</option>
          </select>
        </Box>
        <FormControlLabel
          control={<Switch checked={form.intervention_combination} onChange={event => setField('intervention_combination', event.target.checked)} />}
          label='Regimen / combinazione'
        />
        <TextField label='Policy mode' value={form.policy_mode} onChange={event => setField('policy_mode', event.target.value)} select fullWidth>
          <MenuItem value='strict_verified'>Strict verified</MenuItem>
          <MenuItem value='ontology_aware_warning'>Ontology aware warning</MenuItem>
          <MenuItem value='audit_all'>Audit all</MenuItem>
        </TextField>
        <TextField label='Limite risultati' type='number' slotProps={{ htmlInput: { min: 1, max: 500 } }} value={form.result_limit} onChange={event => setField('result_limit', event.target.value)} fullWidth />
        <Button type='submit' variant='contained' disabled={disabled} sx={{ alignSelf: 'flex-start', fontWeight: 800 }}>
          Esegui pipeline V3
        </Button>
      </Stack>
    </Box>
  );
}
