import { Accordion, AccordionDetails, AccordionSummary, Box, Button, Chip, Stack, Tooltip, Typography } from '@mui/material';
import ExpandMore from '@mui/icons-material/ExpandMore';
import AutoStoriesOutlined from '@mui/icons-material/AutoStoriesOutlined';
import { Fragment, memo, useState } from 'react';
import { color, font, radius, reasonLabel } from './tokens';
import DocumentaryObservation from './DocumentaryObservation';
import type { DocumentaryFinding } from './contracts.generated';

/**
 * Vista narrativa verificata.
 *
 * Il frontend non decide **nulla**: legge `presentation_mode`, deciso dal
 * Narrative Verifier deterministico nel backend. Se la narrativa non e' stata
 * verificata non viene mostrata, e al suo posto compare il motivo.
 *
 * E' la stessa regola che ha chiuso ISS-003 per le quote: la fonte
 * dell'accettazione sta nel backend, mai in un'inferenza del client.
 */

export type PresentationMode = 'VERIFIED_NARRATIVE' | 'DETERMINISTIC_NARRATIVE_FALLBACK' | 'STRUCTURED_DOSSIER_FALLBACK';

export interface CandidateNarrative {
  candidate_id: string;
  text: string;
}

export interface Narrative {
  narrative_summary?: string | null;
  candidate_narratives?: CandidateNarrative[] | null;
  limitations_summary?: string | null;
  closing_note?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  narrative_hash?: string | null;
}

export interface NarrativeVerification {
  status?: string | null;
  reason_codes?: string[] | null;
  verifier_version?: string | null;
  narrative_hash?: string | null;
  input_hash?: string | null;
}

export interface PresentationSource {
  paper_id: string;
  evidence_id?: string | null;
  support_result?: string | null;
  source_unit_id?: string | null;
  quote_available: boolean;
  validated_quote?: string | null;
  source_unit_text?: string | null;
}

export interface CandidatePresentation {
  documentary_contract_version?: string | null;
  documentary_findings?: DocumentaryFinding[] | null;
  candidate_id: string;
  intervention?: string | null;
  graph_relation: string;
  canonical_status: string;
  support_direction: string;
  documentary_support_state: string;
  sources: PresentationSource[];
  critical_notices: string[];
  diagnostic_scope?: string | null;
  diagnostic_context?: {
    device_id?: string;
    device_name?: string;
    drug?: string;
    gene?: string;
    platform_type?: string;
    specimen_types?: string;
  };
  generated_explanation?: string | null;
}

const RELATION_LABELS: Record<string, string> = {
  associated_with_sensitivity_to: 'Associazione con sensibilità/risposta',
  associated_with_resistance_to: 'Associazione con resistenza',
  gene_drug_interaction: 'Interazione gene-farmaco',
  trial_association: 'Associazione a trial clinico',
  has_evidence_statement: 'Relazione descritta nella fonte',
  has_companion_diagnostic: 'Companion diagnostic associato',
};

function relationLabel(relation: string): string {
  return RELATION_LABELS[relation] ?? relation;
}

function candidateTitle(entry: CandidatePresentation): string {
  if (entry.graph_relation === 'has_evidence_statement') return 'Evidenza documentale sul biomarcatore';
  const intervention = entry.intervention?.trim();
  if (intervention && !/^\d+$/.test(intervention)) return intervention;
  if (entry.graph_relation === 'trial_association') return 'Associazione a trial clinico';
  return relationLabel(entry.graph_relation);
}

function documentaryStateLabelForEntry(entry: CandidatePresentation): string {
  if (entry.graph_relation === 'trial_association') {
    if (!['RESOLVED', 'AVAILABLE', 'FULLTEXT_AVAILABLE', 'ABSTRACT_AVAILABLE'].includes(entry.canonical_status)) {
      return 'Record del trial non disponibile o non verificato';
    }
    return entry.sources.some((source) => source.quote_available)
      ? 'Record del trial con citazione disponibile'
      : 'Record del trial disponibile';
  }
  return entry.sources.some(source => source.quote_available) ? 'Citazione disponibile: consultare testo e controlli' : 'Nessuna citazione disponibile in questa vista';
}

function paperLabel(paperId: string): string {
  return paperId.replace(/^pmid:/i, 'PMID ');
}

export interface NarrativePresentation {
  contract_version: string;
  presentation_mode: PresentationMode | string;
  summary?: string | null;
  candidates: CandidatePresentation[];
  canonical_limitations: string[];
  limitations_explanation?: string | null;
  closing_note?: string | null;
  verification?: NarrativeVerification | null;
}

interface Props {
  compact?: boolean;
  showCriticalNotices?: boolean;
  narrative: Narrative | null;
  presentation?: NarrativePresentation | null;
  presentationMode: PresentationMode | string;
  verification: NarrativeVerification | null;
}

function SectionTitle({ children, light = false }: { children: React.ReactNode; light?: boolean }) {
  return (
    <Typography sx={{
      fontFamily: font.mono, fontSize: 11, letterSpacing: '0.08em',
      color: light ? '#fff' : color.slate, textTransform: 'uppercase', mb: 1,
    }}>
      {children}
    </Typography>
  );
}

function NarrativeView({ narrative, presentation, presentationMode, verification, compact = false, showCriticalNotices = true }: Props) {
  const [page, setPage] = useState(0);
  const pageSize = 8;
  const candidateCount = presentation?.candidates.length ?? narrative?.candidate_narratives?.length ?? 0;
  const currentPage = Math.min(page, Math.max(0, Math.ceil(candidateCount / pageSize) - 1));
  const start = currentPage * pageSize;
  const criticalNotices = showCriticalNotices
    ? [...new Set(presentation?.candidates.flatMap((entry) => entry.critical_notices) ?? [])]
    : [];
  const deterministic = presentationMode === 'DETERMINISTIC_NARRATIVE_FALLBACK'
    && narrative != null && verification?.status === 'PASS';
  const verified = (presentationMode === 'VERIFIED_NARRATIVE' && narrative != null && verification?.status === 'PASS') || deterministic;

  return (
    <Box sx={{
      border: `1px solid ${color.borderLight}`, borderRadius: `${radius.md}px`, p: { xs: 2, md: 3 }, mb: 2,
      minWidth: 0, overflowWrap: 'anywhere',
    }}>
      <Stack direction="row" sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1, mb: 1.5 }}>
        <AutoStoriesOutlined sx={{ color: color.deepGreen }} />
        <Typography component="h2" sx={{
          fontFamily: font.display, fontSize: 20, letterSpacing: '-0.01em', color: color.ink,
        }}>
          Sintesi narrativa del caso
        </Typography>
        <Tooltip title="La verifica controlla la fedeltà al dossier, non la correttezza scientifica, la completezza delle evidenze o l’applicabilità al paziente.">
          <Chip
            label={deterministic ? 'Sintesi dal dossier' : verified ? 'Fedelta al dossier verificata' : 'Vista narrativa non disponibile'}
            size="small"
            sx={{
              height: 20, fontFamily: font.mono, fontSize: 10, borderRadius: '4px',
              backgroundColor: verified ? color.stone : color.canvas,
              color: verified ? color.body : color.muted,
            }}
          />
        </Tooltip>
      </Stack>

      <Typography sx={{ fontFamily: font.body, fontSize: 13, lineHeight: 1.55, color: color.slate, maxWidth: '72ch', mb: 2.5 }}>
        Osservazioni e fonti, con il testo narrativo originale consultabile separatamente. La verifica riguarda la fedelta al dossier, non la validita scientifica. Stati e limitazioni restano verificabili
        nel dossier strutturato e non costituiscono una raccomandazione clinica.
      </Typography>

      {verified ? (
        <>
          {(presentation?.summary ?? narrative.narrative_summary) && (
            <Box component="details" sx={{ mb: 3 }}><summary>Sintesi registrata (contratto originale)</summary>
              <SectionTitle>Testo registrato della run</SectionTitle>
              <Typography sx={{ fontFamily: font.body, fontSize: 15, lineHeight: 1.65, color: color.body, maxWidth: '72ch' }}>
                {presentation?.summary ?? narrative.narrative_summary}
              </Typography>
            </Box>
          )}

          {criticalNotices.length > 0 && (
            <Box role="alert" sx={{ mb: 2 }}>
              <SectionTitle>Avvertenze</SectionTitle>
              {criticalNotices.map((notice) => <Typography key={notice} sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>{reasonLabel(notice)}</Typography>)}
            </Box>
          )}
          {!compact && candidateCount > 0 && <SectionTitle>Evidenze e contesto</SectionTitle>}
          {!compact && (presentation ? presentation.candidates.slice(start, start + pageSize).map((entry) => (
            <Box key={entry.candidate_id} sx={{ mb: 2.5, pb: 2.5, borderBottom: `1px solid ${color.borderLight}` }}>
              <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 0.75 }}>
                <Typography sx={{ fontFamily: font.display, fontSize: 16, color: color.ink }}>
                  {candidateTitle(entry)}
                </Typography>
                <Typography component="span" sx={{ fontFamily: font.body, fontSize: 13, color: color.slate }}>
                  {'Osservazione e fonte'}
                </Typography>
                <Typography component="span" sx={{ fontFamily: font.body, fontSize: 12, color: color.muted }}>
                  · {documentaryStateLabelForEntry(entry)}
                </Typography>
              </Stack>
              <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.slate, mb: 1.25 }}>
                Target nel grafo: {relationLabel(entry.graph_relation)}
              </Typography>
              {entry.critical_notices.length > 0 && (
                <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', mb: 1 }} role="alert">
                  {entry.critical_notices.map((notice) => (
                    <Typography key={notice} sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                      {reasonLabel(notice)}
                    </Typography>
                  ))}
                </Stack>
              )}
              {entry.diagnostic_context && Object.keys(entry.diagnostic_context).length > 0 && (
                <Box sx={{ mb: 1, p: 1, border: `1px solid ${color.borderLight}`, borderRadius: `${radius.sm}px` }}>
                  <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, mb: 0.5 }}>
                    Companion diagnostic
                  </Typography>
                  <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                    {entry.diagnostic_context.device_name || entry.diagnostic_context.device_id || 'Dispositivo non specificato'}
                    {entry.diagnostic_context.drug ? ` · farmaco associato: ${entry.diagnostic_context.drug}` : ''}
                    {entry.diagnostic_context.platform_type ? ` · piattaforma: ${entry.diagnostic_context.platform_type}` : ''}
                    {entry.diagnostic_context.specimen_types ? ` · campione: ${entry.diagnostic_context.specimen_types}` : ''}
                  </Typography>
                </Box>
              )}
              {entry.generated_explanation && (
                <Box component="details"><summary>Spiegazione registrata (contratto originale)</summary><Typography sx={{ fontFamily: font.body, fontSize: 14, lineHeight: 1.65, color: color.body, maxWidth: '72ch', mb: 1.25 }}>
                  {entry.generated_explanation}
                </Typography></Box>
              )}
              {entry.documentary_findings?.map((finding, index) => <DocumentaryObservation key={`${finding.evidence_id ?? index}:${finding.disposition}`} finding={finding} />)}
              {entry.sources.map((source, sourceIndex) => {
                const hasEvidenceDetail = Boolean(source.source_unit_text || (source.quote_available && source.validated_quote));
                return (
                <Fragment key={`${source.evidence_id ?? sourceIndex}-${source.paper_id}-${source.source_unit_id ?? ''}`}>
                  {!hasEvidenceDetail && (
                    <Box sx={{ py: 0.75 }}>
                      <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.body }}>
                        Fonte associata · {paperLabel(source.paper_id)} · Citazione validata: {source.quote_available ? 'disponibile' : 'non disponibile'}
                      </Typography>
                    </Box>
                  )}
                <Accordion sx={{ display: hasEvidenceDetail ? 'block' : 'none', backgroundColor: color.canvas }} disableGutters elevation={0}>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.body }}>
                      Fonte selezionata · {paperLabel(source.paper_id)} · Citazione validata: {source.quote_available ? 'disponibile' : 'non disponibile'}
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    {source.support_result && <Typography sx={{ fontSize: 12, mb: 1 }}>Classificazione tecnica storica: {source.support_result}</Typography>}
                    <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                      <>
                        <Box component="span" sx={{ display: 'block', mb: 0.5 }}>
                          Testo della SourceUnit:
                        </Box>
                        <Box component="span" sx={{ display: 'block', mb: 1 }}>
                          {source.source_unit_text || 'Testo della SourceUnit non disponibile.'}
                        </Box>
                        <Box component="span" sx={{ display: 'block', mb: 0.5 }}>
                          Quote validata: {source.quote_available ? 'sì' : 'no'}
                        </Box>
                        {source.quote_available && source.validated_quote
                          ? source.validated_quote : 'Nessuna citazione validata disponibile.'}
                      </>
                    </Typography>
                  </AccordionDetails>
                </Accordion>
                </Fragment>
                );
              })}
              <Accordion disableGutters elevation={0} sx={{ backgroundColor: color.canvas, mt: 0.5 }}>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.muted }}>
                    Tracciabilità tecnica
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={0.5}>
                    <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
                      Candidate: {entry.candidate_id}
                    </Typography>
                    <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
                      Relazione canonica: {entry.graph_relation}
                    </Typography>
                    <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
                      Classificazione tecnica storica: {entry.canonical_status} · direzione: {entry.support_direction}
                    </Typography>
                  </Stack>
                </AccordionDetails>
              </Accordion>
            </Box>
          )) : (narrative.candidate_narratives ?? []).slice(start, start + pageSize).map((entry) => (
            <Box key={entry.candidate_id} sx={{ mb: 1.5 }}>
              <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>{entry.candidate_id}</Typography>
              <Box component="details"><summary>Testo registrato (contratto originale)</summary><Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>{entry.text}</Typography></Box>
            </Box>
          )))}
          {!compact && candidateCount > pageSize && (
            <Stack component="nav" aria-label="Paginazione delle spiegazioni" direction="row" sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap', mb: 2 }}>
              <Button aria-label="Spiegazioni precedenti" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Precedenti</Button>
              <Typography role="status" sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>Spiegazioni {start + 1}–{Math.min(start + pageSize, candidateCount)} di {candidateCount}</Typography>
              <Button aria-label="Spiegazioni successive" disabled={start + pageSize >= candidateCount} onClick={() => setPage(currentPage + 1)}>Successive</Button>
            </Stack>
          )}

          {(presentation?.canonical_limitations?.length || presentation?.limitations_explanation || narrative.limitations_summary) && (
            <Box sx={{ mt: 2 }}>
              <SectionTitle>Limitazioni</SectionTitle>
              <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                {presentation?.limitations_explanation ?? narrative.limitations_summary}
              </Typography>
              {(presentation?.canonical_limitations ?? []).map((limitation) => (
                <Typography key={limitation} sx={{ mt: 0.5, fontFamily: font.body, fontSize: 12, color: color.slate }}>
                  {reasonLabel(limitation)}
                </Typography>
              ))}
            </Box>
          )}

          {(presentation?.closing_note ?? narrative.closing_note) && (
            <Typography sx={{
              fontFamily: font.body, fontSize: 12, color: color.slate, mt: 1.5, fontStyle: 'italic',
            }}>
              {presentation?.closing_note ?? narrative.closing_note}
            </Typography>
          )}
        </>
      ) : (
        <Box>
          <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body, mb: 1 }}>
            {verification?.status === 'FAIL'
              ? 'La sintesi generata non ha superato la verifica deterministica: il sistema mostra il dossier delle evidenze.'
              : 'La sintesi narrativa non è disponibile per questa run. Consulta il dossier delle evidenze.'}
          </Typography>
          {(verification?.reason_codes ?? []).length > 0 && (
            <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap', mt: 1 }}>
              {(verification?.reason_codes ?? []).map((code) => (
                <Typography key={code} sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                  {reasonLabel(code)}
                </Typography>
              ))}
            </Stack>
          )}
        </Box>
      )}

      {verified && verification?.verifier_version && (
        <Accordion disableGutters elevation={0} sx={{ backgroundColor: color.canvas, mt: 1 }}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.muted }}>
              Verifica e tracciabilità tecnica
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted }}>
          {verification.verifier_version}
          {verification.narrative_hash ? ` · ${verification.narrative_hash.slice(0, 12)}` : ''}
            </Typography>
          </AccordionDetails>
        </Accordion>
      )}
    </Box>
  );
}

export default memo(NarrativeView);
