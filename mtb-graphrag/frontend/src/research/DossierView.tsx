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

interface Enrichment {
  author_claim_quote?: string | null;
  author_context_summary?: string | null;
  abstain?: boolean;
  abstention_reason?: string | null;
  source_unit_id?: string | null;
  paper_id?: string | null;
  model?: string | null;
  prompt_version?: string | null;
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
  case_id?: string;
  case_context?: Record<string, unknown>;
  candidate_therapies?: CandidateTherapy[];
  limitations?: string[];
  provenance?: { gemma_role?: string; gemma_never_decides?: string[] };
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
  const accepted = entry.author_context.filter((e) => e.author_claim_quote);
  const abstained = entry.author_context.filter((e) => !e.author_claim_quote);

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

export default function DossierView({ dossier }: { dossier: Dossier | null }) {
  if (!dossier) {
    return (
      <Typography sx={{ fontFamily: font.body, fontSize: 14, color: color.muted, py: 3 }}>
        Nessun dossier per questa run.
      </Typography>
    );
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
