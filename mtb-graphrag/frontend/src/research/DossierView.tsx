/**
 * Il dossier, nelle tre sezioni che devono restare separate.
 *
 * La separazione non è cosmetica. **A** è ciò che il codice deterministico ha
 * concluso; **B** è ciò che un autore ha scritto in un paper, riportato come
 * citazione; **C** è ciò che il sistema non ha potuto stabilire. Fonderle
 * lascerebbe credere che una citazione confermi uno status, che è precisamente
 * la lettura che l'architettura esiste per impedire.
 *
 * Nessuno di questi valori viene calcolato qui: arrivano dal backend e vengono
 * mostrati.
 */

import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material';
import { color, font, radius, reasonLabel } from './tokens';
import { TERM_TOOLTIPS } from './types';

/**
 * Stato di presentazione deciso dal backend, mai dedotto qui.
 * Vale il vocabolario di `backend/research_pipeline/dossier/builder.py`.
 */
type PresentationState =
  | 'VALIDATED_QUOTE'
  | 'REJECTED_QUOTE'
  | 'ABSTAINED'
  | 'PROPOSED_QUOTE_NOT_VALIDATED';

interface Enrichment {
  author_claim_quote?: string | null;
  author_context_summary?: string | null;
  abstain?: boolean;
  abstention_reason?: string | null;
  source_unit_id?: string | null;
  paper_id?: string | null;
  model?: string | null;
  prompt_version?: string | null;
  presentation_state?: PresentationState | null;
  validation_outcome?: string | null;
  validation_reason_codes?: string[] | null;
}

/**
 * Una quote è presentabile come citazione d'autore **solo** se il validatore
 * deterministico l'ha accettata.
 *
 * La regola precedente era `accepted = e.author_claim_quote != null`, cioè
 * l'esistenza di una stringa. Una quote fabbricata dal modello e rigettata con
 * REJECTED_QUOTE_NOT_FOUND finiva così nel gruppo reso in corsivo sotto
 * «Ciò che gli autori dei paper hanno scritto».
 *
 * In assenza del campo — dossier prodotto da una run precedente al fix — si
 * ricade sul comportamento **conservativo**: non presentabile.
 */
function isValidatedAuthorClaim(e: Enrichment): boolean {
  return e.presentation_state === 'VALIDATED_QUOTE';
}

function isAbstention(e: Enrichment): boolean {
  return e.presentation_state === 'ABSTAINED' || (!e.presentation_state && !e.author_claim_quote);
}

interface Validation {
  paper_id?: string;
  outcome?: string;
  reason_codes?: string[];
}

interface CandidateTherapy {
  candidate_id: string;
  drug: string | null;
  graph_relation: string;
  document_support: { selected_papers?: string[]; excluded_papers?: unknown[] };
  author_context: Enrichment[];
  validation_results: Validation[];
  gate_results: { bucket?: string; support_mask?: Record<string, string> };
  status: string;
  warnings: string[];
}

export interface Dossier {
  run_status?: string;
  case_summary?: Record<string, unknown>;
  retrieval_summary?: Record<string, unknown>;
  paper_evidence?: CanonicalEntry[];
  clinical_trials?: CanonicalEntry[];
  kg_only_relations?: CanonicalEntry[];
  case_id?: string;
  case_context?: Record<string, unknown>;
  candidate_therapies?: CandidateTherapy[];
  limitations?: string[];
  provenance?: { gemma_role?: string; gemma_never_decides?: string[] };
}

interface CanonicalEntry {
  candidate_id: string;
  relation?: string;
  subject?: { label?: string } | null;
  object?: { label?: string } | null;
  document_id?: string | null;
  nct_id?: string | null;
  title?: string | null;
  status?: string | null;
  phase?: string[] | string | null;
  conditions?: unknown[];
  interventions?: unknown[];
  quote?: string | null;
  quote_source_unit_id?: string | null;
  support_level?: string | null;
  evidence_interpretation?: string;
  verification_status?: string;
  document_provenance?: string;
}

function SectionTitle({ letter, children }: { letter: string; children: React.ReactNode }) {
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: 'baseline', mb: 1.5 }}>
      <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted }}>{letter}</Typography>
      <Typography sx={{
        fontFamily: font.mono, fontSize: 11, letterSpacing: '0.08em',
        textTransform: 'uppercase', color: color.muted,
      }}>
        {children}
      </Typography>
    </Stack>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', gap: 2, py: 0.75, borderBottom: `1px solid ${color.hairline}` }}>
      <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate, width: 150, flexShrink: 0 }}>
        {label}
      </Typography>
      <Box sx={{ minWidth: 0, flex: 1 }}>{children}</Box>
    </Box>
  );
}

function Text({ children }: { children: React.ReactNode }) {
  return <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>{children}</Typography>;
}

function Mono({ children }: { children: React.ReactNode }) {
  return <Typography sx={{ fontFamily: font.mono, fontSize: 12, color: color.body, wordBreak: 'break-all' }}>{children}</Typography>;
}

function CandidateCard({ entry }: { entry: CandidateTherapy }) {
  const accepted = entry.author_context.filter(isValidatedAuthorClaim);
  const abstained = entry.author_context.filter(isAbstention);
  // Proposte del modello che il validatore ha scartato. Restano visibili per
  // audit, in una sezione propria, mai fra le citazioni degli autori.
  const rejected = entry.author_context.filter(
    (e) => !isValidatedAuthorClaim(e) && !isAbstention(e),
  );

  return (
    <Box sx={{
      border: `1px solid ${color.borderLight}`, borderRadius: `${radius.md}px`,
      p: 2.5, mb: 2,
    }}>
      <Typography sx={{
        fontFamily: font.display, fontSize: 22, letterSpacing: '-0.01em', color: color.ink,
      }}>
        {entry.drug ?? 'Intervento non denominato'}
      </Typography>
      <Typography sx={{ fontFamily: font.mono, fontSize: 11, color: color.muted, mt: 0.5 }}>
        {entry.candidate_id}
      </Typography>

      {/* A — evidenza deterministica */}
      <Box sx={{ mt: 2.5 }}>
        <SectionTitle letter="A">Evidenza deterministica</SectionTitle>
        <Field label="Relazione del grafo">
          <Tooltip title={TERM_TOOLTIPS.graph_derived}>
            <Box>
              <Mono>{entry.graph_relation || 'non disponibile'}</Mono>
              <Typography sx={{ fontFamily: font.body, fontSize: 11, color: color.slate }}>
                Candidate proposta dal grafo — non ancora prova documentale
              </Typography>
            </Box>
          </Tooltip>
        </Field>
        <Field label="Status">
          <Text>{entry.status}</Text>
        </Field>
        <Field label="Bucket">
          <Mono>{entry.gate_results.bucket ?? 'non disponibile'}</Mono>
        </Field>
        <Field label="Support mask">
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
            {Object.entries(entry.gate_results.support_mask ?? {}).map(([axis, value]) => (
              <Chip key={axis} label={`${axis}: ${value}`} size="small" sx={{
                height: 20, fontFamily: font.mono, fontSize: 10,
                backgroundColor: color.stone, color: color.body, borderRadius: '4px',
              }} />
            ))}
          </Stack>
        </Field>
        <Field label="Paper a supporto">
          <Mono>{(entry.document_support.selected_papers ?? []).join(', ') || 'nessuno'}</Mono>
        </Field>
        {entry.warnings.length > 0 && (
          <Field label="Avvisi">
            <Stack spacing={0.5}>
              {entry.warnings.map((w) => <Text key={w}>{reasonLabel(w)}</Text>)}
            </Stack>
          </Field>
        )}
      </Box>

      {/* B — author context */}
      <Box sx={{ mt: 3, backgroundColor: color.stone, borderRadius: `${radius.sm}px`, p: 2 }}>
        <SectionTitle letter="B">Author context</SectionTitle>
        <Typography sx={{ fontFamily: font.body, fontSize: 11, color: color.slate, mb: 1.5 }}>
          Ciò che gli autori dei paper hanno scritto. Non modifica lo status né i gate.
        </Typography>

        {accepted.map((e, i) => (
          <Box key={`q-${i}`} sx={{ mb: 1.5 }}>
            <Typography sx={{
              fontFamily: font.body, fontSize: 14, color: color.ink,
              borderLeft: `2px solid ${color.coral}`, pl: 1.5, fontStyle: 'italic',
            }}>
              “{e.author_claim_quote}”
            </Typography>
            <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, mt: 0.5, pl: 1.5 }}>
              {e.source_unit_id ?? 'source unit non disponibile'} · {e.paper_id ?? '—'}
            </Typography>
            {e.author_context_summary && (
              <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate, pl: 1.5, mt: 0.5 }}>
                {e.author_context_summary}
              </Typography>
            )}
          </Box>
        ))}

        {abstained.map((e, i) => (
          <Tooltip key={`a-${i}`} title={TERM_TOOLTIPS.abstain}>
            <Box sx={{ mb: 1 }}>
              <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.slate }}>
                Astensione — {e.abstention_reason || 'nessuna frase letterale a supporto'}
              </Typography>
            </Box>
          </Tooltip>
        ))}

        {rejected.length > 0 && (
          <Box sx={{ mt: 1.5, pt: 1.5, borderTop: `1px dashed ${color.borderLight}` }}>
            <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, mb: 0.5 }}>
              PROPOSTE NON VALIDATE — SOLO AUDIT
            </Typography>
            <Typography sx={{ fontFamily: font.body, fontSize: 11, color: color.slate, mb: 1 }}>
              Il modello le ha proposte, il validatore deterministico le ha scartate.
              Non sono citazioni degli autori e non contribuiscono allo status.
            </Typography>
            {rejected.map((e, i) => (
              <Box key={`r-${i}`} sx={{ mb: 1 }}>
                <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap', mb: 0.5 }}>
                  <Chip
                    label={e.validation_outcome ?? 'NON_VALIDATA'}
                    size="small"
                    sx={{
                      height: 20, fontFamily: font.mono, fontSize: 10,
                      backgroundColor: color.canvas, color: color.body, borderRadius: '4px',
                    }}
                  />
                  {(e.validation_reason_codes ?? []).map((code) => (
                    <Chip
                      key={code}
                      label={reasonLabel(code)}
                      size="small"
                      sx={{
                        height: 20, fontFamily: font.mono, fontSize: 10,
                        backgroundColor: color.canvas, color: color.muted, borderRadius: '4px',
                      }}
                    />
                  ))}
                </Stack>
                <Typography sx={{
                  fontFamily: font.body, fontSize: 12, color: color.muted,
                  textDecoration: 'line-through', pl: 1.5,
                }}>
                  {e.author_claim_quote ?? '(nessuna quote)'}
                </Typography>
              </Box>
            ))}
          </Box>
        )}

        {entry.author_context.length === 0 && (
          <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.slate }}>
            Nessun contesto d’autore per questa candidate.
          </Typography>
        )}

        {entry.validation_results.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <Typography sx={{ fontFamily: font.mono, fontSize: 10, color: color.muted, mb: 0.5 }}>
              ESITI DI VALIDAZIONE
            </Typography>
            <Stack direction="row" spacing={0.75} sx={{ flexWrap: 'wrap' }}>
              {entry.validation_results.map((v, i) => (
                <Chip key={i} label={v.outcome ?? 'ignoto'} size="small" sx={{
                  height: 20, fontFamily: font.mono, fontSize: 10,
                  backgroundColor: color.canvas, color: color.body, borderRadius: '4px',
                }} />
              ))}
            </Stack>
          </Box>
        )}
      </Box>
    </Box>
  );
}

function CanonicalSection({ title, entries, kind }: {
  title: string; entries: CanonicalEntry[]; kind: 'paper' | 'trial' | 'kg';
}) {
  return (
    <Box sx={{ mb: 4 }}>
      <Typography sx={{ fontFamily: font.display, fontSize: 24, color: color.ink, mb: 1.5 }}>
        {title}
      </Typography>
      {entries.map((entry) => (
        <Box key={entry.candidate_id} sx={{ py: 2, borderTop: `1px solid ${color.borderLight}` }}>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ justifyContent: 'space-between' }}>
            <Box>
              <Mono>{entry.candidate_id}</Mono>
              <Text>{entry.subject?.label ?? 'Relazione'} → {entry.relation ?? 'non specificata'} → {entry.object?.label ?? 'oggetto non specificato'}</Text>
            </Box>
            <Chip label={entry.support_level ?? entry.verification_status ?? entry.status ?? kind.toUpperCase()} size="small" />
          </Stack>
          {kind === 'paper' && (
            <Box sx={{ mt: 1 }}>
              <Mono>{entry.document_id ?? 'Documento non disponibile'} · {entry.quote_source_unit_id ?? 'SourceUnit non disponibile'}</Mono>
              {entry.quote && <Typography sx={{ mt: 1, pl: 1.5, borderLeft: `2px solid ${color.coral}`, fontStyle: 'italic' }}>“{entry.quote}”</Typography>}
            </Box>
          )}
          {kind === 'trial' && (
            <Box sx={{ mt: 1 }}>
              <Text>{entry.title ?? 'Record trial non disponibile'} · {entry.nct_id ?? 'NCT non disponibile'}</Text>
              <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate }}>
                Associazione a trial; non costituisce prova di efficacia né valutazione di eleggibilità.
              </Typography>
            </Box>
          )}
          {kind === 'kg' && <Text>Provenance documentale: {entry.document_provenance ?? 'NOT_AVAILABLE'}</Text>}
        </Box>
      ))}
      {entries.length === 0 && <Text>Nessuna voce in questa sezione.</Text>}
    </Box>
  );
}

function CanonicalDossierView({ dossier }: { dossier: Dossier }) {
  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', mb: 4 }}>
        <Box>
          <Typography sx={{ fontFamily: font.display, fontSize: 30, color: color.ink }}>Dossier MTB relation-aware</Typography>
          <Text>{String(dossier.case_summary?.disease ?? 'Contesto clinico non disponibile')}</Text>
        </Box>
        <Chip label={dossier.run_status ?? 'COMPLETED'} />
      </Stack>
      <CanonicalSection title="Paper evidence" entries={dossier.paper_evidence ?? []} kind="paper" />
      <CanonicalSection title="Clinical trials" entries={dossier.clinical_trials ?? []} kind="trial" />
      <CanonicalSection title="Relazioni del Knowledge Graph" entries={dossier.kg_only_relations ?? []} kind="kg" />
      <Box sx={{ borderTop: `1px solid ${color.hairline}`, pt: 2 }}>
        <SectionTitle letter="L">Limitazioni</SectionTitle>
        {(dossier.limitations ?? []).map((item) => <Text key={item}>{reasonLabel(item)}</Text>)}
      </Box>
    </Box>
  );
}

export default function DossierView({ dossier }: { dossier: Dossier | null }) {
  if (!dossier) {
    return (
      <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.muted, py: 3 }}>
        Nessun dossier per questa run.
      </Typography>
    );
  }

  if (dossier.paper_evidence || dossier.clinical_trials || dossier.kg_only_relations) {
    return <CanonicalDossierView dossier={dossier} />;
  }

  const candidates = dossier.candidate_therapies ?? [];

  return (
    <Box>
      {candidates.map((entry) => <CandidateCard key={entry.candidate_id} entry={entry} />)}

      {candidates.length === 0 && (
        <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.slate, mb: 2 }}>
          Nessuna candidate terapeutica nel dossier.
        </Typography>
      )}

      {/* C — limitazioni */}
      <Box sx={{ mt: 1, border: `1px solid ${color.hairline}`, borderRadius: `${radius.sm}px`, p: 2 }}>
        <SectionTitle letter="C">Limitazioni</SectionTitle>
        <Stack spacing={0.5}>
          {(dossier.limitations ?? []).map((l) => (
            <Typography key={l} sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>
              {reasonLabel(l)}
            </Typography>
          ))}
        </Stack>
        {dossier.provenance?.gemma_never_decides && (
          <Typography sx={{ fontFamily: font.body, fontSize: 12, color: color.slate, mt: 1.5 }}>
            Il modello non decide: {dossier.provenance.gemma_never_decides.join(', ')}.
          </Typography>
        )}
      </Box>
    </Box>
  );
}
