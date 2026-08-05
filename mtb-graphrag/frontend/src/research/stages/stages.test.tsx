/**
 * Le viste di stage, su preview della forma che il backend produce davvero.
 *
 * I dati di questi test sono ricopiati da una run reale di
 * `CASE-1-therapy-evaluation-strong-match`: una forma inventata avrebbe
 * verificato il componente contro l'idea che me ne sono fatto, non contro ciò
 * che arriva. Il difetto `[object Object]` era emerso esattamente lì, su chiavi
 * annidate che nessun dato di test costruiva.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import StageOutput from './index';
import { expectNoObjectObject } from '../values/testing';
import type { PipelineStage, StageProducer } from '../types';

const DETERMINISTIC: StageProducer = {
  kind: 'DETERMINISTIC', component: 'x', version: 'v1', model: null, prompt_version: null,
};

const LLM: StageProducer = {
  kind: 'LLM', component: 'paper_context_enricher_v2', version: 'paper-context-enricher/2.0',
  model: 'gemma4:cloud', prompt_version: 'paper-context-enricher-prompt/2.0',
  transport_version: 'paper-context-enrichment-transport/2.0',
};

function stage(overrides: Partial<PipelineStage>): PipelineStage {
  return {
    stage_id: 'stage_1_case_input', stage_type: 'CASE_INPUT', sequence: 1,
    status: 'SUCCEEDED', started_at: null, completed_at: null, duration_ms: 4,
    input_preview: {}, output_preview: {}, reason_codes: [], warnings: [], errors: [],
    producer: DETERMINISTIC, metrics: {}, lineage: {},
    ...overrides,
  };
}

describe('CaseContext Match Verifier', () => {
  const matchStage = stage({
    stage_id: 'stage_3_casecontext_match', stage_type: 'CASECONTEXT_MATCH_VERIFIER', sequence: 3,
    output_preview: {
      essential_fields_pass: true,
      warnings: [],
      records: [{
        field: 'disease', casecontext_value: 'Colorectal Cancer', status: 'MATCH',
        supporting_text: 'metastatic colorectal cancer', start_offset: 14, end_offset: 42,
        reason_code: 'EXACT_SUBSTRING',
      }],
    },
  });

  it('mostra il campo, il testo di supporto e gli offset', () => {
    render(<StageOutput stage={matchStage} clinicalText="A patient with metastatic colorectal cancer" />);
    expect(screen.getByText('disease')).toBeInTheDocument();
    expect(screen.getByText('14–42')).toBeInTheDocument();
    // Il testo di supporto compare fra virgolette; il testo clinico integrale,
    // mostrato sopra, contiene la stessa sottostringa.
    expect(screen.getByText(/“metastatic colorectal cancer”/)).toBeInTheDocument();
  });

  it('mostra lo stato del confronto e il suo reason code', () => {
    render(<StageOutput stage={matchStage} />);
    expect(screen.getByText('MATCH')).toBeInTheDocument();
    expect(screen.getByText('EXACT_SUBSTRING')).toBeInTheDocument();
  });
});

describe('Graph Candidate Assertion', () => {
  const retrievalStage = stage({
    stage_id: 'stage_5_kg_retrieval', stage_type: 'KG_RETRIEVAL', sequence: 5,
    output_preview: {
      graph_derived: true, documentary_proof: false, no_match: false,
      associations: [{
        candidate_id: 'GCA-008ae3aad1a64c118318ef79',
        candidate: {
          disease: 'Colorectal Cancer',
          biomarkers: [{ label: 'KRAS G12D' }],
          interventions: [{ label: 'panitumumab' }],
          direction: 'Resistance',
          predicate: 'associated_with_resistance_to',
        },
        match_reason_codes: ['DISEASE_EXACT', 'BIOMARKER_EXACT'],
        available_bundles: [{ bundle_id: 'EB-1', document_id: 'pmid:19223544' }],
      }],
      excluded_candidates: [],
    },
  });

  it('avverte che la candidate non è ancora prova documentale', () => {
    render(<StageOutput stage={retrievalStage} />);
    expect(screen.getAllByText('GRAPH-DERIVED').length).toBeGreaterThan(0);
    expect(screen.getByText(/non è ancora evidenza documentale/i)).toBeInTheDocument();
  });

  it('non usa il vocabolario della pipeline precedente', () => {
    const { container } = render(<StageOutput stage={retrievalStage} />);
    expect(container.textContent).not.toMatch(/qualified claim/i);
  });

  it('rende i biomarcatori annidati senza coercizione', () => {
    const { container } = render(<StageOutput stage={retrievalStage} />);
    expect(container.textContent).toContain('KRAS G12D');
    expectNoObjectObject(container);
  });

  it('dichiara esplicitamente un NO_MATCH', () => {
    const noMatch = stage({
      ...retrievalStage,
      output_preview: { ...retrievalStage.output_preview, associations: [], no_match: true },
    });
    render(<StageOutput stage={noMatch} />);
    expect(screen.getByText('NO_MATCH')).toBeInTheDocument();
  });
});

describe('Paper Context Enricher', () => {
  const quote = 'patients with mCRC bearing KRAS mutations are clinically resistant';

  const withQuote = stage({
    stage_id: 'stage_9_paper_context_enricher', stage_type: 'PAPER_CONTEXT_ENRICHER',
    sequence: 9, producer: LLM,
    output_preview: {
      calls: [{
        candidate_id: 'GCA-1', paper_id: 'EB-1', model: 'gemma4:cloud',
        prompt_version: 'paper-context-enricher-prompt/2.0',
        transport_version: 'paper-context-enrichment-transport/2.0',
        transport_result: 'V2_TRANSPORT_VALID',
        input_tokens: 1638, output_tokens: 120, latency_ms: 3662.4, replayed: true,
        enrichment: {
          author_claim_quote: quote, source_unit_id: 'SU-1',
          author_context_summary: 'Resistenza riportata dagli autori.',
        },
      }],
    },
  });

  it('mostra la decisione QUOTE con la citazione proposta', () => {
    render(<StageOutput stage={withQuote} />);
    expect(screen.getByText('QUOTE')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(quote))).toBeInTheDocument();
  });

  it('dichiara modello, prompt e transport version reali', () => {
    render(<StageOutput stage={withQuote} />);
    expect(screen.getByText('gemma4:cloud')).toBeInTheDocument();
    expect(screen.getByText('paper-context-enricher-prompt/2.0')).toBeInTheDocument();
    expect(screen.getByText('paper-context-enrichment-transport/2.0')).toBeInTheDocument();
  });

  it('dichiara che il modello non assegna status né gate', () => {
    render(<StageOutput stage={withQuote} />);
    expect(screen.getByText(/Non assegna status, direzione, gate o bucket/i)).toBeInTheDocument();
  });

  it('mostra ABSTAIN con il suo motivo, senza citazione', () => {
    const abstained = stage({
      ...withQuote,
      output_preview: {
        calls: [{
          candidate_id: 'GCA-1', paper_id: 'EB-2',
          enrichment: { author_claim_quote: null, abstention_reason: 'NO_LITERAL_SUPPORT' },
        }],
      },
    });
    render(<StageOutput stage={abstained} />);
    expect(screen.getByText('ABSTAIN')).toBeInTheDocument();
    expect(screen.getByText('NO_LITERAL_SUPPORT')).toBeInTheDocument();
  });
});

describe('Enrichment Validation', () => {
  function validationStage(outcome: string) {
    return stage({
      stage_id: 'stage_10_enrichment_validation', stage_type: 'ENRICHMENT_VALIDATION', sequence: 10,
      output_preview: {
        accepted_outcomes: ['ENRICHMENT_V2_ACCEPTED'],
        validations: [{ candidate_id: 'GCA-1', paper_id: 'EB-1', outcome, reason_codes: [] }],
      },
    });
  }

  it('segna una quote accettata come ammessa nel dossier', () => {
    render(<StageOutput stage={validationStage('ENRICHMENT_V2_ACCEPTED')} />);
    // L'esito compare due volte: fra quelli ammessi e come esito di questa
    // validazione. Entrambe le occorrenze sono corrette.
    expect(screen.getAllByText('ENRICHMENT_V2_ACCEPTED').length).toBeGreaterThan(0);
    expect(screen.getByText('ENTRA NEL DOSSIER')).toBeInTheDocument();
  });

  it('mantiene visibile una quote rigettata, ma fuori dal dossier', () => {
    render(<StageOutput stage={validationStage('REJECTED_QUOTE_NOT_FOUND')} />);
    expect(screen.getByText('REJECTED_QUOTE_NOT_FOUND')).toBeInTheDocument();
    expect(screen.getByText('NON ENTRA NEL DOSSIER')).toBeInTheDocument();
  });

  it('dichiara che astensioni e rigetti non toccano status o bucket', () => {
    render(<StageOutput stage={validationStage('ENRICHMENT_V2_ABSTAINED')} />);
    expect(screen.getByText(/non influenzano status, mask, bucket o score/i)).toBeInTheDocument();
  });
});

describe('Controlli deterministici', () => {
  const checksStage = stage({
    stage_id: 'stage_11_deterministic_gates', stage_type: 'DETERMINISTIC_GATES', sequence: 11,
    output_preview: {
      checks_by_candidate: [{
        candidate_id: 'GCA-1',
        support_mask: { disease: 'SUPPORTED', direction: 'SUPPORTED' },
        direction_consistencies: ['CONSISTENT'],
        checks: [
          {
            check_id: 'disease', label: 'Malattia', source: 'INHERITED_VERIFIED_RESULT',
            result: 'SUPPORTED', reason_code: 'SUPPORTED',
            source_stage: 'stage_5_kg_retrieval', evidence_ref: null,
            version: 'deterministic-checks/1.0',
          },
          {
            check_id: 'direction', label: 'Direzione dell’evidenza', source: 'COMPUTED_HERE',
            result: 'SUPPORTED', reason_code: 'SUPPORTED',
            source_stage: 'stage_11_deterministic_gates', evidence_ref: null,
            version: 'deterministic-checks/1.0',
          },
          {
            check_id: 'source_gate', label: 'Source gate', source: 'NOT_IMPLEMENTED',
            result: null, reason_code: 'CHECK_DEFINED_IN_DESIGN_BUT_NOT_IMPLEMENTED',
            source_stage: null, evidence_ref: null, version: 'deterministic-checks/1.0',
          },
        ],
      }],
    },
  });

  it('distingue un esito ereditato da uno calcolato qui', () => {
    render(<StageOutput stage={checksStage} />);
    expect(screen.getByText('INHERITED_VERIFIED_RESULT')).toBeInTheDocument();
    expect(screen.getByText('COMPUTED_HERE')).toBeInTheDocument();
    expect(screen.getByText('stage_5_kg_retrieval')).toBeInTheDocument();
  });

  it('elenca i controlli non implementati invece di ometterli', () => {
    render(<StageOutput stage={checksStage} />);
    expect(screen.getByText('NOT_IMPLEMENTED')).toBeInTheDocument();
    expect(screen.getByText('Source gate')).toBeInTheDocument();
  });

  it('non attribuisce uno stage di origine a un controllo non implementato', () => {
    const { container } = render(<StageOutput stage={checksStage} />);
    expectNoObjectObject(container);
  });
});

describe('Stage non eseguiti', () => {
  it('distingue "non implementato" da un output vuoto', () => {
    const narrator = stage({
      stage_id: 'stage_14_narrator', stage_type: 'DOSSIER_NARRATOR', sequence: 14,
      status: 'SKIPPED', reason_codes: ['NOT_IMPLEMENTED'],
    });
    render(<StageOutput stage={narrator} />);
    // Badge in testa e reason code in coda: due occorrenze volute.
    expect(screen.getAllByText('NOT_IMPLEMENTED').length).toBeGreaterThan(0);
    expect(screen.getByText(/dichiararlo eseguito sarebbe simulazione/i)).toBeInTheDocument();
  });

  it('dice perché uno stage a valle di un arresto non è stato eseguito', () => {
    const skipped = stage({
      stage_id: 'stage_9_paper_context_enricher', stage_type: 'PAPER_CONTEXT_ENRICHER',
      sequence: 9, status: 'SKIPPED', reason_codes: ['RETRIEVAL_NO_MATCH'],
    });
    render(<StageOutput stage={skipped} />);
    expect(screen.getByText('NOT_EXECUTED')).toBeInTheDocument();
    expect(screen.getByText(/il grafo non propone candidate/i)).toBeInTheDocument();
  });
});

describe('Source Unit', () => {
  it('mostra locatori e hash, mai il testo', () => {
    const units = stage({
      stage_id: 'stage_7_source_units', stage_type: 'SOURCE_UNIT', sequence: 7,
      output_preview: {
        replayed: true,
        source_units: [{
          source_unit_id: 'SU-12a97ff4', unit_type: 'ABSTRACT_SENTENCE',
          document_id: 'pmid:19223544', section: null, paragraph_index: null,
          sentence_index: 0, char_start: 0, char_end: 192,
          content_hash: '12a97ff4a9065ff0947b17c7104bb84151c22d56',
          parser: 'PubMedAbstractParser', parser_version: '1.0',
        }],
      },
    });
    const { container } = render(<StageOutput stage={units} />);

    expect(screen.getByText('ABSTRACT_SENTENCE')).toBeInTheDocument();
    expect(screen.getByText('0–192')).toBeInTheDocument();
    expect(screen.getByText('NESSUN TESTO')).toBeInTheDocument();
    expectNoObjectObject(container);
  });
});
