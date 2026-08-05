/**
 * Il contratto di resa dei valori strutturati.
 *
 * Il difetto che questi test esistono per impedire è preciso: `String(value)` e
 * l'interpolazione in template su un oggetto producono `[object Object]`, che
 * nella Supervisor UI non è un difetto estetico. Uno stage che mostra
 * `[object Object]` al posto di un CaseContext o di una support mask ha smesso
 * di essere ispezionabile, ed è indistinguibile da uno stage che non ha
 * prodotto nulla.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import StructuredValue from './StructuredValue';
import { expectNoObjectObject } from './testing';

describe('StructuredValue — primitive', () => {
  it('mostra una stringa come testo leggibile', () => {
    render(<StructuredValue value="ENRICHMENT_V2_ACCEPTED" />);
    expect(screen.getByText('ENRICHMENT_V2_ACCEPTED')).toBeInTheDocument();
  });

  it('mostra i numeri, incluso lo zero', () => {
    const { container } = render(<StructuredValue value={0} />);
    expect(container.textContent).toContain('0');
  });

  it('distingue false da assente', () => {
    render(<StructuredValue value={false} />);
    expect(screen.getByText('false')).toBeInTheDocument();
  });

  it('dice che un valore nullo non è disponibile', () => {
    render(<StructuredValue value={null} />);
    expect(screen.getByText('Non disponibile')).toBeInTheDocument();
  });

  it('tratta undefined come non disponibile', () => {
    render(<StructuredValue value={undefined} />);
    expect(screen.getByText('Non disponibile')).toBeInTheDocument();
  });
});

describe('StructuredValue — array', () => {
  it('dichiara un array vuoto invece di non mostrare nulla', () => {
    render(<StructuredValue value={[]} />);
    expect(screen.getByText('Nessun elemento')).toBeInTheDocument();
  });

  it('rende un array di primitive come elementi distinti', () => {
    render(<StructuredValue value={['DIRECT', 'PARTIAL']} />);
    expect(screen.getByText('DIRECT')).toBeInTheDocument();
    expect(screen.getByText('PARTIAL')).toBeInTheDocument();
  });

  it('rende un array di oggetti come tabella con una colonna per chiave', () => {
    const rows = [
      { candidate_id: 'GCA-1', status: 'DIRECT' },
      { candidate_id: 'GCA-2', status: 'AMBIGUOUS' },
    ];
    const { container } = render(<StructuredValue value={rows} />);

    expect(container.querySelector('table')).not.toBeNull();
    expect(screen.getByText('GCA-1')).toBeInTheDocument();
    expect(screen.getByText('AMBIGUOUS')).toBeInTheDocument();
    expectNoObjectObject(container);
  });

  it('non produce [object Object] con oggetti annidati in un array', () => {
    const rows = [{ candidate: { id: 'GCA-1', biomarkers: [{ label: 'KRAS G12D' }] } }];
    const { container } = render(<StructuredValue value={rows} />);
    expectNoObjectObject(container);
  });
});

describe('StructuredValue — oggetti', () => {
  it('rende un oggetto piatto come coppie chiave/valore', () => {
    render(<StructuredValue value={{ disease: 'Colorectal Cancer', intent: 'THERAPY_EVALUATION' }} />);
    expect(screen.getByText('disease')).toBeInTheDocument();
    expect(screen.getByText('Colorectal Cancer')).toBeInTheDocument();
  });

  it('non produce [object Object] su un oggetto profondamente annidato', () => {
    const value = {
      case_context: {
        disease: { normalized_value: 'Colorectal Cancer', source_span: { start: 14, end: 31 } },
        biomarkers: [{ normalized_value: 'KRAS G12D', evidence: { span: [1, 2] } }],
      },
    };
    const { container } = render(<StructuredValue value={value} />);
    expectNoObjectObject(container);
    expect(container.textContent).toContain('KRAS G12D');
  });

  it('dichiara un oggetto vuoto invece di rendere una riga muta', () => {
    render(<StructuredValue value={{}} />);
    expect(screen.getByText('Nessun campo')).toBeInTheDocument();
  });
});

describe('StructuredValue — nessun valore diventa [object Object]', () => {
  const shapes: Array<[string, unknown]> = [
    ['oggetto nudo', { a: 1 }],
    ['array di oggetti', [{ a: 1 }, { b: 2 }]],
    ['oggetto con array di oggetti', { rows: [{ a: { b: 1 } }] }],
    ['array di array', [[1, 2], [3, 4]]],
    ['oggetto con null', { a: null, b: { c: null } }],
    ['array misto', [1, 'x', { y: 2 }, null]],
    ['mappa di oggetti', { first: { x: 1 }, second: { y: 2 } }],
  ];

  it.each(shapes)('%s', (_label, value) => {
    const { container } = render(<StructuredValue value={value} />);
    expectNoObjectObject(container);
  });
});
