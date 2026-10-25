import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DossierView from './DossierView';
import type { DocumentaryFinding } from './contracts.generated';
import DocumentaryObservation from './DocumentaryObservation';
import { reasonLabel } from './tokens';
import controlledPublications from '../../../backend/research_pipeline/tests/fixtures/msi_controlled_cached_publications.json';

const finding: DocumentaryFinding = {
  evidence_id: 'E1', candidate_id: 'C1', disposition: 'EXCLUDED_RECORD',
  source: { paper_id: 'pmid:123', source_unit_id: 'SU1' }, quotation: 'No response was observed.',
  observed: { effect_direction: 'RESISTANCE' }, observed_origin: 'READER_EXTRACTION_NOT_INDEPENDENT_GOLD',
  checks: { quotation: { status: 'AUTHENTICATED' }, structural: { status: 'UNRESOLVED' }, semantic: { status: 'NOT_EXECUTED' } },
  limitations: { reason_codes: ['GENE_VARIANT_PAIR_NOT_ADJACENT'] },
  scientific_correctness: 'NOT_INDEPENDENTLY_EVALUATED', clinical_applicability: 'NOT_EVALUATED',
};

describe('canonical documentary contract rendering', () => {
  const identityNotice = 'La corrispondenza di identità non dimostra un effetto terapeutico specifico.';
  const scopeNotice = 'Il risultato aggregato non stabilisce un effetto specifico per il sottogruppo MSI-H.';
  function phenotypeFinding(operator: string, span: string | null): DocumentaryFinding {
    return { ...finding, disposition: 'RETAINED_RECORD', observed: { observed_relation: { subjects: [{ type: 'BIOMARKER', surface_value: 'MSI-H' }] } },
      checks: { ...finding.checks, correspondence: { fields: { phenotype: 'CONFIRMED' }, phenotype_scope: {
        logical_operator: operator, literal_span: span, population_relation: operator === 'OR' ? 'BROADER_OR_ALTERNATIVE' : operator === 'AND' ? 'INTERSECTION' : 'UNKNOWN', subgroup_effect_established: false,
      } } } };
  }
  it.each([['OR', 'MSI-H or dMMR', 'oppure'], ['AND', 'MSI-H and dMMR', 'entrambi']])('shows %s scope literally with recorded notices once', (operator, span, explanation) => {
    render(<DocumentaryObservation finding={phenotypeFinding(operator, span)} reading={{ paper_index: 0, finding_index: 0, disease_text_comparison: 'NOT_RECORDED', intervention_text_comparison: 'NOT_RECORDED', notices: [{ code: 'PHENOTYPE_IDENTITY_CORRESPONDENCE', message: identityNotice }, { code: 'PHENOTYPE_ALTERNATIVE_POPULATION', message: scopeNotice }] }} />);
    expect(screen.getByText('Identità del fenotipo nella fonte: corrispondenza confermata')).toBeInTheDocument();
    expect(screen.getByText(span)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`Popolazione della fonte:.*${explanation}`))).toBeInTheDocument();
    expect(screen.getAllByText(identityNotice)).toHaveLength(1);
    expect(screen.getAllByText(scopeNotice)).toHaveLength(1);
    expect(screen.queryByText(/Supporto documentale completo|FULL_SUPPORT/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Gene/)).not.toBeInTheDocument();
  });
  it('keeps unknown scope and null literal explicit without inventing a population', () => {
    render(<DocumentaryObservation finding={phenotypeFinding('UNKNOWN', null)} />);
    expect(screen.getByText('Popolazione della fonte: rapporto non stabilito')).toBeInTheDocument();
    expect(screen.getByText('Passaggio letterale sulla popolazione: non registrato')).toBeInTheDocument();
    expect(screen.queryByText('MSI-H or dMMR')).not.toBeInTheDocument();
  });
  it('preserves the cached publication quote and BIOMARKER without inventing a gene or subgroup efficacy', () => {
    // Actual cached text with controlled Reader output, not a real model run.
    const publication = controlledPublications.results[0];
    const record = phenotypeFinding('OR', 'MSI-H or dMMR');
    record.quotation = publication.reader_observation.quote;
    record.observed = publication.reader_observation.observed_relation;
    render(<DocumentaryObservation finding={record} />);
    expect(screen.getByText(publication.source_unit.text)).toBeInTheDocument();
    expect(screen.getByText('MSI-H')).toBeInTheDocument();
    expect(screen.getByText(/non stabiliscono un effetto terapeutico specifico per il sottogruppo/)).toBeInTheDocument();
    expect(screen.queryByText(/^Gene/)).not.toBeInTheDocument();
    expect(screen.queryByText(/FULL_SUPPORT|Supporto documentale completo/)).not.toBeInTheDocument();
  });
  it('does not add phenotype rows to an existing gene observation without optional data', () => {
    render(<DocumentaryObservation finding={{ ...finding, observed: { subjects: [{ type: 'GENE', surface_value: 'BRAF' }] } }} />);
    expect(screen.queryByText(/Identità del fenotipo|Popolazione della fonte/)).not.toBeInTheDocument();
    expect(screen.getByText('BRAF')).toBeInTheDocument();
  });
  it.each(['NARRATIVE_OBSERVATION_CHECK_MISMATCH', 'NARRATIVE_OBSERVATION_VARIANT_ESCALATION', 'NARRATIVE_OBSERVATION_CAUSAL_ESCALATION', 'NARRATIVE_PATIENT_ELIGIBILITY_UNASSESSED', 'NARRATIVE_OBSERVATION_REGIMEN_UNPROVEN', 'NARRATIVE_OBSERVATION_PHENOTYPE_SCOPE_OMITTED'])('translates %s for the normal view', code => {
    expect(reasonLabel(code)).not.toBe(code);
  });
  it('preserves excluded observations and actual checks without promoting a legacy verdict', () => {
    render(<DossierView debug={false} dossier={{ documentary_contract_version: 'documentary-findings/1.0', paper_evidence: [{ candidate_id: 'C1', support_level: 'FULL_SUPPORT', documentary_findings: [finding] }] }} />);
    expect(screen.getByText('Record escluso')).toBeInTheDocument();
    expect(screen.getByText('No response was observed.')).toBeInTheDocument();
    expect(screen.getByText(/Gate: UNRESOLVED/)).toHaveTextContent('Semantica: Non eseguita');
    expect(screen.getByText('Resistenza riportata')).toBeInTheDocument();
    const schema = screen.getByText('Schema originale e tracciabilità').closest('details')!;
    schema.open = true;
    fireEvent(schema, new Event('toggle'));
    expect(screen.getByText('E1')).toBeInTheDocument();
    expect(screen.getByText('RESISTANCE')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'pmid:123' })).toHaveAttribute('href', 'https://pubmed.ncbi.nlm.nih.gov/123/');
    expect(screen.queryByText('Supporto documentale completo')).not.toBeInTheDocument();
  });
  it('retains abstention details even without any observation', () => {
    render(<DossierView debug={false} dossier={{ paper_evidence: [{ candidate_id: 'C1', documentary_findings: [], documentary_attempts: [{ decision: 'ABSTAIN', abstain_reason: 'NO_RELEVANT_EVIDENCE' }] }] }} />);
    const details = screen.getByText(/Tentativi Reader e operazioni/).closest('details')!;
    details.open = true;
    fireEvent(details, new Event('toggle'));
    expect(screen.getByText('NO_RELEVANT_EVIDENCE')).toBeInTheDocument();
    expect(screen.getByText(/Nessuna osservazione documentale conservata/)).toBeInTheDocument();
  });
});
