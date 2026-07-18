import { useState } from 'react';
import {
  Card,
  Tabs,
  Tab,
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Button,
  CircularProgress,
  Grid,
  CardContent
} from '@mui/material';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import SchemaIcon from '@mui/icons-material/Schema';
import PsychologyIcon from '@mui/icons-material/Psychology';
import MedicineIcon from '@mui/icons-material/Medication';
import BiotechIcon from '@mui/icons-material/Biotech';
import SearchIcon from '@mui/icons-material/Search';
import AutoStoriesIcon from '@mui/icons-material/AutoStories';
import type { ReportResponse } from '../types';
import KnowledgeGraph3D from './KnowledgeGraph3D';

interface StructuredDataProps {
  data: ReportResponse;
  onEnrich?: () => void;
  enriching?: boolean;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

export default function StructuredData({ data, onEnrich, enriching }: StructuredDataProps) {
  const [tabValue, setTabValue] = useState(0);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  return (
    <Card variant="outlined">
      <Box sx={{ borderBottom: 1, borderColor: 'divider', bgcolor: '#F8FAFC' }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ '& .MuiTabs-indicator': { height: 3 } }}
        >
          <Tab icon={<SchemaIcon />} iconPosition="start" label="Activated KB Graph" />
          <Tab icon={<PsychologyIcon />} iconPosition="start" label="Pipeline Trace (Thought)" />
          <Tab label={`Drug Candidates (${data.drug_candidates.length})`} />
          <Tab label={`Resistance Profile (${data.resistance_data.length})`} />
          <Tab label={`Clinical Trials (${data.trial_candidates.length})`} />
          <Tab label={`OncoKB Enrichment (${data.oncokb_enrichment?.length || 0})`} />
        </Tabs>
      </Box>

      {/* --- TAB 0: GRAFO 3D --- */}
      <TabPanel value={tabValue} index={0}>
        <KnowledgeGraph3D data={data} />
      </TabPanel>

      {/* --- TAB 1: PIPELINE TRACE --- */}
      <TabPanel value={tabValue} index={1}>
        <Box sx={{ bgcolor: '#FAF5FF', p: 2.5, borderRadius: 2, border: '1px solid #F3E8FF', mb: 3 }}>
          <Typography variant="subtitle2" color="secondary" sx={{ fontWeight: 700 }}>
            Visualizzatore della Traccia Agentica (Thought Trace)
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Mostra la sequenza di passaggi logici e decisionali eseguiti dai vari agenti coordinati in LangGraph.
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0, pl: 2 }}>
          {[
            {
              stage: 'Stage 1',
              title: 'Complexity Checker',
              description: 'Riconoscimento e instradamento del caso clinico.',
              icon: <SearchIcon fontSize="small" sx={{ color: '#FFFFFF' }} />,
              color: '#1E3A8A',
              content: (
                <Chip label={`Complexity: ${data.complexity.toUpperCase()}`} size="small" color="primary" sx={{ mt: 1 }} />
              )
            },
            {
              stage: 'Stage 2',
              title: 'Variant Interpreter',
              description: 'Classificazione della mutazione e assegnazione dello score ESCAT.',
              icon: <BiotechIcon fontSize="small" sx={{ color: '#FFFFFF' }} />,
              color: '#059669',
              content: (
                <Chip label={`ESCAT Tier: ${data.complexity === 'zero-shot' ? 'N/A' : data.escat_tier || 'N/D'}`} size="small" color="success" sx={{ mt: 1 }} />
              )
            },
            {
              stage: 'Stage 3',
              title: 'Target Identifier',
              description: 'Estrazione farmaci di sensibilità e companion diagnostics.',
              icon: <MedicineIcon fontSize="small" sx={{ color: '#FFFFFF' }} />,
              color: '#06B6D4',
              content: (
                <Box component="span" sx={{ display: 'block', mt: 1, fontSize: '0.75rem', color: 'text.secondary' }}>
                  {data.complexity === 'zero-shot'
                    ? 'Nessun database locale consultato'
                    : `Trovati ${data.drug_candidates.length} candidati attivi`}
                </Box>
              )
            },
            {
              stage: 'Stage 4',
              title: 'Trial Matcher',
              description: 'Interrogazione del registro NCT per studi clinici attivi.',
              icon: <SearchIcon fontSize="small" sx={{ color: '#FFFFFF' }} />,
              color: '#7C3AED',
              content: (
                <Box component="span" sx={{ display: 'block', mt: 1, fontSize: '0.75rem', color: 'text.secondary' }}>
                  {data.complexity === 'zero-shot'
                    ? 'Nessun database locale consultato'
                    : `Individuati ${data.trial_candidates.length} studi eleggibili`}
                </Box>
              )
            },
            {
              stage: 'Stage 5',
              title: 'Resistance Checker',
              description: 'Verifica mutazioni secondarie e mitigazione Retrieval Pollution.',
              icon: <BiotechIcon fontSize="small" sx={{ color: '#FFFFFF' }} />,
              color: '#DC2626',
              content: (
                <Box component="span" sx={{ display: 'block', mt: 1, fontSize: '0.75rem', color: 'text.secondary' }}>
                  {data.complexity === 'zero-shot'
                    ? 'Nessun database locale consultato'
                    : `Rilevati ${data.resistance_data.length} profili di resistenza`}
                </Box>
              )
            },
            {
              stage: 'Stage 6',
              title: 'Synthesizer',
              description: 'Verifica bibliografica finale dei PMID e composizione del report.',
              icon: <AutoStoriesIcon fontSize="small" sx={{ color: '#FFFFFF' }} />,
              color: '#D97706',
              content: (
                <Chip label={`${data.cited_pmids.length} citazioni finali`} size="small" color="warning" sx={{ mt: 1 }} />
              )
            }
          ].map((stage, idx, arr) => {
            const isLast = idx === arr.length - 1;
            return (
              <Box key={idx} sx={{ display: 'flex', minHeight: 90 }}>
                <Box sx={{ width: 80, pr: 2, pt: '4px', textAlign: 'right', flexShrink: 0 }}>
                  <Typography variant="caption" sx={{ fontWeight: 700, color: 'text.secondary' }}>
                    {stage.stage}
                  </Typography>
                </Box>

                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', mr: 3, flexShrink: 0 }}>
                  <Box sx={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    bgcolor: stage.color,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: `0 2px 6px ${stage.color}60`,
                    zIndex: 1
                  }}>
                    {stage.icon}
                  </Box>
                  {!isLast && (
                    <Box sx={{ width: 2, flexGrow: 1, bgcolor: '#E2E8F0', my: 0.5 }} />
                  )}
                </Box>

                <Box sx={{ pb: isLast ? 2 : 4, pt: '4px' }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#1E293B' }}>
                    {stage.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                    {stage.description}
                  </Typography>
                  {stage.content}
                </Box>
              </Box>
            );
          })}
        </Box>
      </TabPanel>

      {/* --- TAB 2: DRUG CANDIDATES --- */}
      <TabPanel value={tabValue} index={2}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Farmaco</TableCell>
                <TableCell>Approvato</TableCell>
                <TableCell>Livello Evidenza</TableCell>
                <TableCell>Comp. Diagnostic</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.drug_candidates.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary', fontStyle: 'italic' }}>
                    Nessun farmaco trovato nel KG
                  </TableCell>
                </TableRow>
              ) : data.drug_candidates.map((drug, idx) => (
                <TableRow key={idx}>
                  <TableCell sx={{ fontWeight: 600 }}>{drug.drug_name}</TableCell>
                  <TableCell>
                    <Chip label={drug.approved ? 'Sì' : 'No'} size="small" color={drug.approved ? 'success' : 'default'} />
                  </TableCell>
                  <TableCell>{drug.evidence_level}</TableCell>
                  <TableCell>{drug.companion_diagnostic || '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </TabPanel>

      {/* --- TAB 3: RESISTANCE PROFILE --- */}
      <TabPanel value={tabValue} index={3}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Variante</TableCell>
                <TableCell>Livello</TableCell>
                <TableCell>Tumore</TableCell>
                <TableCell width="50%">Statement</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.resistance_data.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary', fontStyle: 'italic' }}>
                    Nessuna evidenza di resistenza nel KG
                  </TableCell>
                </TableRow>
              ) : data.resistance_data.map((res, idx) => (
                <TableRow key={idx}>
                  <TableCell><b>{res.variant}</b></TableCell>
                  <TableCell>{res.evidence_level}</TableCell>
                  <TableCell>{res.disease}</TableCell>
                  <TableCell><Typography variant="body2">{res.statement}</Typography></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </TabPanel>

      {/* --- TAB 4: CLINICAL TRIALS --- */}
      <TabPanel value={tabValue} index={4}>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>NCT ID</TableCell>
                <TableCell>Fase</TableCell>
                <TableCell>Stato</TableCell>
                <TableCell>Titolo</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.trial_candidates.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} align="center" sx={{ py: 4, color: 'text.secondary', fontStyle: 'italic' }}>
                    Nessun trial eleggibile nel KG
                  </TableCell>
                </TableRow>
              ) : data.trial_candidates.map((trial, idx) => (
                <TableRow key={idx}>
                  <TableCell>
                    <a href={`https://clinicaltrials.gov/ct2/show/${trial.nct_id}`} target="_blank" rel="noreferrer" style={{ color: '#1E40AF', fontWeight: 600 }}>
                      {trial.nct_id}
                    </a>
                  </TableCell>
                  <TableCell>{trial.phase}</TableCell>
                  <TableCell>
                    <Chip label={trial.status} size="small" variant="outlined" />
                  </TableCell>
                  <TableCell><Typography variant="body2">{trial.title}</Typography></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </TabPanel>

      {/* --- TAB 5: ONCOKB ENRICHER --- */}
      <TabPanel value={tabValue} index={5}>
        {data.oncokb_enrichment === null || data.oncokb_enrichment === undefined ? (
          <Box sx={{ p: 4, textAlign: 'center', bgcolor: '#F8FAFC', borderRadius: 2, border: '1px dashed #CBD5E1' }}>
            <AutoAwesomeIcon sx={{ fontSize: 48, color: '#94A3B8', mb: 2 }} />
            <Typography variant="h6" gutterBottom color="text.secondary">
              Nessun dato OncoKB presente
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3, maxWidth: 500, mx: 'auto' }}>
              Puoi interrogare le API live di OncoKB per cercare ulteriori evidenze o farmaci off-label non presenti nel Knowledge Graph.
            </Typography>
            {onEnrich && (
              <Button
                variant="contained"
                color="primary"
                onClick={onEnrich}
                disabled={enriching}
                startIcon={enriching ? <CircularProgress size={20} color="inherit" /> : <AutoAwesomeIcon />}
                sx={{ px: 4, py: 1 }}
                disableElevation
              >
                {enriching ? 'Ricerca in corso...' : 'Interroga OncoKB Ora'}
              </Button>
            )}
          </Box>
        ) : data.oncokb_enrichment.length === 0 ? (
          <Box sx={{ p: 4, textAlign: 'center', bgcolor: '#FEF2F2', borderRadius: 2, border: '1px solid #FECACA' }}>
            <Typography variant="subtitle1" color="error.main" sx={{ fontWeight: 700 }}>
              Nessun nuovo trattamento LEVEL_1 o LEVEL_2 trovato
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              OncoKB non ha restituito farmaci con alto livello di evidenza non già presenti nel report.
            </Typography>
          </Box>
        ) : (
          <Grid container spacing={3}>
            {data.oncokb_enrichment.map((res, idx) => (
              <Grid size={{ xs: 12, md: 6 }} key={idx}>
                <Card variant="outlined" sx={{ height: '100%', borderColor: '#E2E8F0', transition: 'box-shadow 0.2s', '&:hover': { borderColor: '#94A3B8', boxShadow: '0 4px 12px rgba(0,0,0,0.07)' } }}>
                  <Box sx={{ p: 2, borderBottom: '1px solid #F1F5F9', bgcolor: '#F8FAFC', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#0F172A' }}>
                      {res.drugs.join(' + ')}
                    </Typography>
                    <Chip
                      label={res.level}
                      size="small"
                      sx={{
                        fontWeight: 700,
                        bgcolor: res.level === 'LEVEL_1' ? '#059669' : '#D97706',
                        color: 'white'
                      }}
                    />
                  </Box>
                  <CardContent sx={{ p: 2 }}>
                    <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Tumore Associato
                    </Typography>
                    <Typography variant="body2" sx={{ mb: 2, fontWeight: 600, color: '#334155' }}>
                      {res.cancer_type || 'N/D'}
                    </Typography>

                    <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Descrizione OncoKB
                    </Typography>
                    <Typography variant="body2" sx={{ color: '#475569', mt: 0.5 }}>
                      {res.description}
                    </Typography>

                    {res.pmids && res.pmids.length > 0 && (
                      <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid #F1F5F9' }}>
                        <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700, display: 'block', mb: 1, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          Fonti (PMID)
                        </Typography>
                        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                          {res.pmids.slice(0, 5).map(pmid => (
                            <Chip
                              key={pmid}
                              label={pmid}
                              size="small"
                              variant="outlined"
                              component="a"
                              href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}`}
                              target="_blank"
                              clickable
                              sx={{ fontSize: '0.7rem' }}
                            />
                          ))}
                          {res.pmids.length > 5 && (
                            <Chip label={`+${res.pmids.length - 5}`} size="small" variant="outlined" sx={{ fontSize: '0.7rem' }} />
                          )}
                        </Box>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </TabPanel>
    </Card>
  );
}
