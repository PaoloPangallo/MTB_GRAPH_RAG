import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import NarrativeView from './NarrativeView';

const NARRATIVE = {
  narrative_summary: 'Il sistema ha identificato una candidate.',
  candidate_narratives: [
    { candidate_id: 'GCA-1', text: 'La relazione con PANITUMUMAB rimane ambigua.' },
  ],
  limitations_summary: 'Prototipo di ricerca.',
  closing_note: 'Materiale per revisione in Molecular Tumor Board.',
  narrative_hash: 'abcdef0123456789',
};

const VERIFIED = { status: 'PASS', reason_codes: [], verifier_version: 'narrative-verifier/1.0' };
const PRESENTATION = {
  contract_version: 'narrative-presentation/2.0',
  presentation_mode: 'VERIFIED_NARRATIVE',
  summary: NARRATIVE.narrative_summary,
  candidates: [{
    candidate_id: 'GCA-1', intervention: 'PANITUMUMAB',
    graph_relation: 'associated_with_resistance_to', canonical_status: 'AMBIGUOUS',
    support_direction: 'NO_DOCUMENT_SIGNAL',
    documentary_support_state: 'NO_VALIDATED_DOCUMENTARY_EVIDENCE',
    sources: [{ paper_id: 'PMID-1', source_unit_id: 'SU-1', quote_available: true,
                validated_quote: 'validated quote', source_unit_text: 'complete source unit text' }],
    critical_notices: ['NO_VALIDATED_ENRICHMENT_AVAILABLE'],
    generated_explanation: 'La relazione con PANITUMUMAB rimane ambigua.',
  }],
  canonical_limitations: ['research_only_pilot'],
  limitations_explanation: NARRATIVE.limitations_summary,
  closing_note: NARRATIVE.closing_note,
  verification: VERIFIED,
};

describe('NarrativeView', () => {
  it('mostra la narrativa quando il backend la dichiara verificata', () => {
    render(<NarrativeView narrative={NARRATIVE} presentation={PRESENTATION} presentationMode="VERIFIED_NARRATIVE"
                          verification={VERIFIED} />);

    expect(screen.getByText('VERIFICATA')).toBeInTheDocument();
    expect(screen.getByText(/La relazione con PANITUMUMAB rimane ambigua/)).toBeInTheDocument();
    expect(screen.getByText(/GCA-1 · associated_with_resistance_to/)).toBeInTheDocument();
    expect(screen.getByText('PANITUMUMAB')).toBeInTheDocument();
    expect(screen.getByText('AMBIGUOUS')).toBeInTheDocument();
    expect(screen.getByText('Nessun supporto documentale validato')).toBeInTheDocument();
    expect(screen.getByText(/Fonte selezionata: PMID-1 · SU-1/)).toBeInTheDocument();
    expect(screen.getByText('Quote validata: sì')).toBeInTheDocument();
    expect(screen.getByText('validated quote')).toBeInTheDocument();
    expect(screen.getByText('complete source unit text')).toBeInTheDocument();
  });

  it('NON mostra la narrativa quando il verifier ha fallito', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL',
                                          reason_codes: ['NARRATIVE_STATUS_ESCALATION'] }} />);

    expect(screen.queryByText(/La relazione con PANITUMUMAB rimane ambigua/)).not.toBeInTheDocument();
    expect(screen.getByText(/NON DISPONIBILE — FALLBACK STRUTTURATO/)).toBeInTheDocument();
  });

  it('mostra il motivo del fallimento invece della narrativa', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL',
                                          reason_codes: ['NARRATIVE_UNAUTHORIZED_ENTITY'] }} />);

    expect(screen.getByText(/non ha superato la verifica deterministica/)).toBeInTheDocument();
    expect(screen.getByText(/NARRATIVE_UNAUTHORIZED_ENTITY/)).toBeInTheDocument();
  });

  it('non mostra nulla quando la narrativa e assente', () => {
    render(<NarrativeView narrative={null} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL', reason_codes: ['NARRATIVE_ABSENT'] }} />);

    expect(screen.getByText(/NON DISPONIBILE/)).toBeInTheDocument();
    expect(screen.getByText(/Il dossier strutturato qui sopra resta completo/)).toBeInTheDocument();
  });

  it('non promuove una narrativa presente ma non verificata', () => {
    // presentation_mode e' l'unica fonte: la presenza del payload non basta.
    render(<NarrativeView narrative={NARRATIVE} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL', reason_codes: [] }} />);

    expect(screen.queryByText('VERIFICATA')).not.toBeInTheDocument();
    expect(screen.queryByText(/Il sistema ha identificato una candidate/)).not.toBeInTheDocument();
  });

  it('dichiara che la narrativa non modifica lo stato canonico', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="VERIFIED_NARRATIVE"
                          verification={VERIFIED} />);

    expect(screen.getByText(/Non modifica status, gate/)).toBeInTheDocument();
  });
});
