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

describe('NarrativeView', () => {
  it('mostra la narrativa quando il backend la dichiara verificata', () => {
    render(<NarrativeView narrative={NARRATIVE} presentationMode="VERIFIED_NARRATIVE"
                          verification={VERIFIED} />);

    expect(screen.getByText('VERIFICATA')).toBeInTheDocument();
    expect(screen.getByText(/La relazione con PANITUMUMAB rimane ambigua/)).toBeInTheDocument();
    expect(screen.getByText('GCA-1')).toBeInTheDocument();
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
