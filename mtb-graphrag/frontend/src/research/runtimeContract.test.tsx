import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import StageOutput from './stages';
import { makeStage } from './testFactories';
import fixture from './__fixtures__/runtime-contract.json';
import DossierView, { type Dossier } from './DossierView';
import CanonicalProvenance from './CanonicalProvenance';
import { SSE_EVENT_TYPES } from './types';

describe('payload prodotti dal runtime Python', () => {
  it('sottoscrive tutti gli eventi nominati del runtime', () => {
    expect([...SSE_EVENT_TYPES].sort()).toEqual([...fixture.event_types].sort());
  });
  it('mantiene distinti i tre rami delle candidate reali GCA4 senza documenti risolti', () => {
    render(<DossierView dossier={fixture.unresolved_report as unknown as Dossier} />);
    expect(screen.getByRole('heading', { name: /^Evidenze da pubblicazioni/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^Studi clinici/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /^Relazioni del Knowledge Graph/ })).toBeInTheDocument();
    expect(screen.getAllByText(/dettagli della relazione/).length).toBeGreaterThan(0);
    expect(screen.queryByText('Supporto non verificabile')).not.toBeInTheDocument();
    expect(screen.getByText('UNAVAILABLE')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /This was a retrospective study/ })).not.toBeInTheDocument();
  });
  it('traccia le claim canoniche e la provenienza del grafo senza usare gli status legacy', () => {
    render(<CanonicalProvenance dossier={fixture.unresolved_report as unknown as Dossier} />);
    for (const candidate of [...fixture.unresolved_report.paper_evidence, ...fixture.unresolved_report.clinical_trials, ...fixture.unresolved_report.kg_only_relations]) {
      expect(screen.getAllByText(candidate.candidate_id).length).toBeGreaterThan(0);
    }
  });
  it('legge locatori, lineage e anteprima testuale della Source Unit reale', () => {
    render(<StageOutput stage={makeStage({ stage_id: 'stage_7_source_units', output_preview: {
      source_units: [fixture.source_unit], documents_parsed: 1, text_never_exposed: true,
    } })} />);
    expect(screen.getByText('Results')).toBeInTheDocument();
    expect(screen.getByText(/parser-contract/)).toBeInTheDocument();
    expect(screen.getByText(/Grounded passage from the document/)).toBeInTheDocument();
    expect(screen.queryByText('NESSUN TESTO')).not.toBeInTheDocument();
  });
  it('non confonde cache miss con documenti non disponibili', () => {
    render(<StageOutput stage={makeStage({ stage_id: 'stage_6_document_resolution', output_preview: {
      documents: [], cache_hits: 1, cache_misses: 0, network_fetch_count: 0, unavailable_count: 1,
    } })} />);
    expect(screen.getByText('NON DISPONIBILI 1')).toBeInTheDocument();
  });
  it('mostra solo il report canonico nello stage dossier', () => {
    render(<StageOutput stage={makeStage({ stage_id: 'stage_13_dossier', output_preview: {
      relation_aware_report: fixture.empty_report,
      dossier: { candidate_therapies: [{ status: 'LEGACY_STATUS_SHOULD_NOT_RENDER' }] },
    } })} />);
    expect(screen.getByRole('heading', { name: 'Dossier canonico' })).toBeInTheDocument();
    expect(screen.queryByText('LEGACY_STATUS_SHOULD_NOT_RENDER')).not.toBeInTheDocument();
  });
});
