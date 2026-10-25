import { fireEvent, render, screen } from '@testing-library/react';
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
     diagnostic_scope: 'CompanionDiagnostic',
     diagnostic_context: {
       device_name: 'Abbott RealTime IDH1', drug: 'Ivosidenib', platform_type: 'PCR',
       specimen_types: 'Bone marrow;Peripheral Blood',
     },
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
  it('keeps compact summaries bounded while preserving limitations and warnings', () => {
    render(<NarrativeView compact narrative={NARRATIVE} presentation={PRESENTATION}
      presentationMode="VERIFIED_NARRATIVE" verification={VERIFIED} />);
    expect(screen.getByText(NARRATIVE.narrative_summary)).toBeInTheDocument();
    expect(screen.getByText(NARRATIVE.limitations_summary)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText(PRESENTATION.candidates[0].generated_explanation)).not.toBeInTheDocument();
    expect(screen.queryByText('Evidenze e contesto')).not.toBeInTheDocument();
  });

  it('labels an evidence statement by its role instead of displaying its claim as a drug', () => {
    render(<NarrativeView narrative={NARRATIVE} presentation={{ ...PRESENTATION, candidates: [{
      ...PRESENTATION.candidates[0], graph_relation: 'has_evidence_statement', intervention: 'A long documentary claim',
    }] }} presentationMode="VERIFIED_NARRATIVE" verification={VERIFIED} />);
    expect(screen.getByText('Evidenza documentale sul biomarcatore')).toBeInTheDocument();
    expect(screen.queryByText('A long documentary claim')).not.toBeInTheDocument();
  });

  it('shows critical notices from candidates outside the current page', () => {
    const candidates = Array.from({ length: 9 }, (_, index) => ({
      ...PRESENTATION.candidates[0], candidate_id: `notice-${index}`,
      critical_notices: index === 8 ? ['UNIQUE_OFF_PAGE_WARNING'] : [],
    }));
    const { rerender } = render(<NarrativeView narrative={NARRATIVE}
      presentation={{ ...PRESENTATION, candidates }} presentationMode="VERIFIED_NARRATIVE" verification={VERIFIED} />);
    expect(screen.getByRole('alert')).toHaveTextContent('UNIQUE_OFF_PAGE_WARNING');
    rerender(<NarrativeView showCriticalNotices={false} narrative={NARRATIVE}
      presentation={{ ...PRESENTATION, candidates }} presentationMode="VERIFIED_NARRATIVE" verification={VERIFIED} />);
    expect(screen.queryByText('UNIQUE_OFF_PAGE_WARNING')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Spiegazioni successive' }));
    expect(screen.getByRole('alert')).toHaveTextContent('UNIQUE_OFF_PAGE_WARNING');
  });

  it('paginates every candidate in accessible pages of eight', () => {
    const candidates = Array.from({ length: 17 }, (_, index) => ({
      ...PRESENTATION.candidates[0], candidate_id: `candidate-${index}`,
      intervention: `Intervento ${index + 1}`, generated_explanation: `Spiegazione ${index + 1}`,
    }));
    render(<NarrativeView narrative={NARRATIVE} presentation={{ ...PRESENTATION, candidates }}
      presentationMode="VERIFIED_NARRATIVE" verification={VERIFIED} />);
    expect(screen.getByText('Spiegazioni 1–8 di 17')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Spiegazioni precedenti' })).toBeDisabled();
    expect(screen.queryByText('Spiegazione 9')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Spiegazioni successive' }));
    expect(screen.getByText('Spiegazione 9')).toBeInTheDocument();
    expect(screen.queryByText('Spiegazione 1')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Spiegazioni successive' }));
    expect(screen.getByText('Spiegazione 17')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Spiegazioni successive' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Spiegazioni precedenti' }));
    expect(screen.getByText('Spiegazione 9')).toBeInTheDocument();
  });

  it('distingue la sintesi deterministica dal successo del narratore', () => {
    render(<NarrativeView narrative={NARRATIVE} presentation={PRESENTATION}
      presentationMode="DETERMINISTIC_NARRATIVE_FALLBACK" verification={VERIFIED} />);
    expect(screen.getByText('Sintesi dal dossier')).toBeInTheDocument();
    expect(screen.queryByText('Narrativa verificata')).not.toBeInTheDocument();
    expect(screen.getByText(/La relazione con PANITUMUMAB rimane ambigua/)).toBeInTheDocument();
  });
  it('non mostra un fallback deterministico respinto', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="DETERMINISTIC_NARRATIVE_FALLBACK"
      verification={{ ...VERIFIED, status: 'FAIL' }} />);
    expect(screen.queryByText(/La relazione con PANITUMUMAB rimane ambigua/)).not.toBeInTheDocument();
  });
  it('non presenta un identificativo trial come record risolto', () => {
    render(<NarrativeView presentationMode="VERIFIED_NARRATIVE" verification={VERIFIED}
      narrative={NARRATIVE} presentation={{ ...PRESENTATION, candidates: [{
        ...PRESENTATION.candidates[0], graph_relation: 'trial_association', canonical_status: 'UNAVAILABLE',
        sources: [{ paper_id: 'NCT05176665', quote_available: false }],
      }] }} />);
    expect(screen.queryByText('Record del trial disponibile')).not.toBeInTheDocument();
    expect(screen.getByText(/Record del trial non disponibile o non verificato/)).toBeInTheDocument();
  });
  it('mostra la narrativa quando il backend la dichiara verificata', () => {
    render(<NarrativeView narrative={NARRATIVE} presentation={PRESENTATION} presentationMode="VERIFIED_NARRATIVE"
                          verification={VERIFIED} />);

    expect(screen.getByText('Fedelta al dossier verificata')).toBeInTheDocument();
    expect(screen.getByText('Sintesi narrativa del caso')).toBeInTheDocument();
    expect(screen.getByText('Evidenze e contesto')).toBeInTheDocument();
    expect(screen.getByText(/La relazione con PANITUMUMAB rimane ambigua/)).toBeInTheDocument();
    expect(screen.getByText(/Associazione con resistenza/)).toBeInTheDocument();
    expect(screen.getByText('PANITUMUMAB')).toBeInTheDocument();
    expect(screen.queryByText('Non conclusivo')).not.toBeInTheDocument();
    expect(screen.getByText(/Citazione disponibile: consultare testo e controlli/)).toBeInTheDocument();
    expect(screen.getByText(/Fonte selezionata · PMID-1 · Citazione validata: disponibile/)).toBeInTheDocument();
    expect(screen.getByText('validated quote')).toBeInTheDocument();
    expect(screen.getByText('complete source unit text')).toBeInTheDocument();
    expect(screen.getByText('Companion diagnostic')).toBeInTheDocument();
    expect(screen.getByText(/Abbott RealTime IDH1 · farmaco associato: Ivosidenib · piattaforma: PCR/)).toBeInTheDocument();
  });

  it('NON mostra la narrativa quando il verifier ha fallito', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL',
                                          reason_codes: ['NARRATIVE_STATUS_ESCALATION'] }} />);

    expect(screen.queryByText(/La relazione con PANITUMUMAB rimane ambigua/)).not.toBeInTheDocument();
    expect(screen.getByText('Vista narrativa non disponibile')).toBeInTheDocument();
  });

  it('mostra il motivo del fallimento invece della narrativa', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL',
                                          reason_codes: ['NARRATIVE_UNAUTHORIZED_ENTITY'] }} />);

    expect(screen.getByText(/non ha superato la verifica deterministica/)).toBeInTheDocument();
    expect(screen.getByText("La spiegazione contiene un'entità non autorizzata")).toBeInTheDocument();
  });

  it('non mostra nulla quando la narrativa e assente', () => {
    render(<NarrativeView narrative={null} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL', reason_codes: ['NARRATIVE_ABSENT'] }} />);

    expect(screen.getByText('Vista narrativa non disponibile')).toBeInTheDocument();
    expect(screen.getByText(/Consulta il dossier delle evidenze|il sistema mostra il dossier delle evidenze/)).toBeInTheDocument();
  });

  it('non promuove una narrativa presente ma non verificata', () => {
    // presentation_mode e' l'unica fonte: la presenza del payload non basta.
    render(<NarrativeView narrative={NARRATIVE} presentationMode="STRUCTURED_DOSSIER_FALLBACK"
                          verification={{ status: 'FAIL', reason_codes: [] }} />);

    expect(screen.queryByText('Narrativa verificata')).not.toBeInTheDocument();
    expect(screen.queryByText(/Il sistema ha identificato una candidate/)).not.toBeInTheDocument();
  });

  it('dichiara che la narrativa non modifica lo stato canonico', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="VERIFIED_NARRATIVE"
                          verification={VERIFIED} />);

    expect(screen.getByText(/La verifica riguarda la fedelta al dossier/)).toBeInTheDocument();
  });
});


it.each(['FAIL', 'UNKNOWN', undefined])('hides prose without PASS verification (%s)', (status) => {
  render(<NarrativeView narrative={NARRATIVE} presentation={PRESENTATION} presentationMode="VERIFIED_NARRATIVE" verification={{ status }} />);
  expect(screen.queryByText(NARRATIVE.narrative_summary)).not.toBeInTheDocument();
  expect(screen.queryByText('Narrativa verificata')).not.toBeInTheDocument();
});
