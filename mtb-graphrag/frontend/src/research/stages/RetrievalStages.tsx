/**
 * Stage 5-8: candidate del grafo, documenti, SourceUnit, selezione dei paper.
 *
 * Il vocabolario qui è deliberato. Ciò che il grafo propone è una
 * **GraphCandidateAssertion**, non un Qualified Claim: è un'associazione
 * asserita da un knowledge graph, non un'affermazione sostenuta da un documento
 * letto. La distinzione regge tutto ciò che segue — la selezione dei paper, la
 * citazione, la validazione — e chiamarla "claim" a questo punto la annullerebbe
 * prima ancora che un documento venga aperto.
 */

import { Box, Stack, Typography } from '@mui/material';
import StructuredValue from '../values/StructuredValue';
import { color, font } from '../tokens';
import {
  Badge, Card, Empty, Field, GraphDerivedWarning, Mono, Note, num, ReasonCodeList,
  ReplayBadge, SectionLabel, rows, text,
} from './kit';

interface StageProps {
  preview: Record<string, unknown>;
}

export function GraphCandidateStage({ preview }: StageProps) {
  const associations = rows(preview, 'associations');
  const excluded = rows(preview, 'excluded_candidates');
  const noMatch = preview.no_match === true;

  return (
    <Box>
      <GraphDerivedWarning />

      {noMatch && (
        <Card>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
            <Badge label="NO_MATCH" tone="neutral" />
          </Stack>
          <Typography sx={{ fontFamily: font.body, fontSize: 13, color: color.body }}>
            Il grafo non propone alcuna candidate compatibile con questo CaseContext.
            La pipeline si ferma qui senza costruire evidenza: è l’esito corretto,
            non un guasto.
          </Typography>
        </Card>
      )}

      <SectionLabel>Candidate ammesse ({associations.length})</SectionLabel>
      {associations.length === 0 && !noMatch && <Empty>Nessuna candidate</Empty>}

      {associations.map((association, index) => {
        const candidate = association.candidate as Record<string, unknown> | undefined;
        const bundles = Array.isArray(association.available_bundles) ? association.available_bundles : [];

        return (
          <Card key={index}>
            <Mono>{text(association.candidate_id) ?? `candidate ${index + 1}`}</Mono>
            <Box sx={{ mt: 1.5 }}>
              <Field label="Malattia"><StructuredValue value={candidate?.disease} /></Field>
              <Field label="Biomarcatori"><StructuredValue value={candidate?.biomarkers} /></Field>
              <Field label="Interventi"><StructuredValue value={candidate?.interventions} /></Field>
              <Field label="Direzione (grafo)">
                <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
                  <StructuredValue value={candidate?.direction} />
                  <Badge label="GRAPH-DERIVED" tone="warn" />
                </Stack>
              </Field>
              <Field label="Relazione"><StructuredValue value={candidate?.predicate} /></Field>
              <Field label="Motivo del match">
                <ReasonCodeList codes={association.match_reason_codes} />
              </Field>
              <Field label="Documenti collegati">
                <Mono>{bundles.length}</Mono>
              </Field>
            </Box>
          </Card>
        );
      })}

      <Box sx={{ mt: 3 }}>
        <SectionLabel>Candidate escluse ({excluded.length})</SectionLabel>
        <Note>Perché il grafo le ha proposte e il filtro strutturale le ha respinte.</Note>
        {excluded.length === 0
          ? <Empty>Nessuna esclusione</Empty>
          : <StructuredValue value={excluded} />}
      </Box>
    </Box>
  );
}

export function DocumentResolutionStage({ preview }: StageProps) {
  const documents = rows(preview, 'documents');
  // Cosa è successo davvero in questa run, letto dallo stage che lo ha fatto.
  // Qui compariva un badge REPLAY incondizionato e la frase «documenti risolti
  // in una run precedente»: era vera del runtime che non risolveva affatto i
  // documenti, ed è rimasta a descrivere un percorso che nel frattempo li
  // risolve. Una didascalia sbagliata su un dato giusto è peggio di nessuna
  // didascalia, perché viene letta al posto del dato.
  const cacheHits = num(preview.cache_hits) ?? 0;
  const cacheMisses = num(preview.cache_misses) ?? 0;
  const fetched = num(preview.network_fetch_count) ?? 0;
  const replayed = preview.replayed === true;

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5, flexWrap: 'wrap' }}>
        {replayed && <ReplayBadge />}
        {cacheHits > 0 && <Badge label={`CACHE HIT ${cacheHits}`} tone="good"
          title="Documento già presente nella cache autorizzata: nessuna chiamata di rete." />}
        {fetched > 0 && <Badge label={`API ${fetched}`}
          title="Documento assente dalla cache e acquisito ora da una fonte autorizzata, poi persistito." />}
        {cacheMisses > fetched && <Badge label={`NON DISPONIBILI ${cacheMisses - fetched}`} tone="warn"
          title="Il documento non è stato ottenuto. Nessun artefatto viene messo al suo posto." />}
      </Stack>

      <SectionLabel>Documenti ({documents.length})</SectionLabel>
      <Note>
        Cache-first: un documento già in cache viene letto da lì, altrimenti
        viene acquisito da una fonte autorizzata e lo snapshot è persistito prima
        del parsing. Se non si ottiene, resta non disponibile: la pipeline non
        inventa una fonte per colmare il vuoto e non ne rigioca una registrata.
      </Note>

      {documents.length === 0
        ? <Empty>Nessun documento risolto</Empty>
        : <StructuredValue value={documents} />}
    </Box>
  );
}

export function SourceUnitStage({ preview }: StageProps) {
  const units = rows(preview, 'source_units');

  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1.5, flexWrap: 'wrap' }}>
        {preview.replayed === true && <ReplayBadge />}
        {(num(preview.documents_parsed) ?? 0) > 0 && (
          <Badge label={`PARSED ${num(preview.documents_parsed)}`} tone="good"
            title="Documenti ri-parsati dal proprio snapshot durante questa run." />
        )}
        <Badge label="NESSUN TESTO" title="Ciò che esce di qui contiene solo locatori e content_hash: il testo del documento non transita mai per l'API." />
      </Stack>

      <SectionLabel>Source Unit ({units.length})</SectionLabel>
      <Note>
        Ogni unità porta tipo, posizione nel documento e hash del contenuto. Il
        testo non compare: l’indice non lo contiene, e mostrarlo qui
        significherebbe far uscire il documento dall’enricher.
      </Note>

      {units.length === 0 && <Empty>Nessuna Source Unit risolta</Empty>}

      {units.map((unit, index) => (
        <Card key={index}>
          <Mono>{text(unit.source_unit_id) ?? `unit ${index + 1}`}</Mono>
          <Box sx={{ mt: 1 }}>
            <Field label="Tipo">
              {text(unit.unit_type) ? <Badge label={text(unit.unit_type)!} /> : <Empty>non disponibile</Empty>}
            </Field>
            <Field label="Documento"><StructuredValue value={unit.document_id} /></Field>
            <Field label="Sezione"><StructuredValue value={unit.section} /></Field>
            <Field label="Indice">
              <Mono>
                paragrafo {String(unit.paragraph_index ?? '—')} · frase {String(unit.sentence_index ?? '—')}
              </Mono>
            </Field>
            <Field label="Locatore">
              <Mono>{String(unit.char_start ?? '—')}–{String(unit.char_end ?? '—')}</Mono>
            </Field>
            <Field label="Content hash">
              <Mono>{text(unit.content_hash)?.slice(0, 24) ?? 'non disponibile'}…</Mono>
            </Field>
            <Field label="Parser">
              <Mono>{text(unit.parser) ?? '—'} {text(unit.parser_version) ?? ''}</Mono>
            </Field>
          </Box>
        </Card>
      ))}
    </Box>
  );
}

export function PaperSelectionStage({ preview }: StageProps) {
  const selections = rows(preview, 'selections');
  const max = preview.max_papers_per_association;

  return (
    <Box>
      <SectionLabel>Selezione deterministica</SectionLabel>
      <Note>
        I paper sono scelti da criteri ordinati, non dal modello. L’enricher
        riceve le Source Unit dei soli paper selezionati e non può sceglierne
        altri.
      </Note>
      <Field label="Massimo per candidate"><StructuredValue value={max} /></Field>

      {selections.length === 0 && <Empty>Nessuna selezione</Empty>}

      {selections.map((selection, index) => {
        const selected = Array.isArray(selection.selected_papers) ? selection.selected_papers : [];
        const excluded = Array.isArray(selection.excluded_papers) ? selection.excluded_papers : [];

        return (
          <Card key={index}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', mb: 1 }}>
              <Mono>{text(selection.candidate_id) ?? `candidate ${index + 1}`}</Mono>
              {selection.replayed === true && <ReplayBadge />}
            </Stack>

            <Field label="Criteri applicati">
              <StructuredValue value={selection.criteria_order} />
            </Field>
            <Field label={`Paper selezionati (${selected.length})`}>
              {selected.length === 0
                ? <Empty>Nessun paper selezionato</Empty>
                : <StructuredValue value={selected} />}
            </Field>
            <Field label={`Paper esclusi (${excluded.length})`}>
              {excluded.length === 0
                ? <Empty>Nessuna esclusione</Empty>
                : <StructuredValue value={excluded} />}
            </Field>
          </Card>
        );
      })}
    </Box>
  );
}
