'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const data = require('../data.js');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {JSDOM} = createRequire(path.resolve(__dirname,'../../../../../mtb-graphrag/frontend/package.json'))('jsdom');
test('ogni approfondimento espone operazioni specifiche, senza il diagramma segnaposto', () => {
  for (const phase of data.phases) {
    const labels = phase.flow.nodes.map(n => n.title).join('\n');
    assert.doesNotMatch(labels, /Controllare il passaggio|Segnalare un limite|se utilizzabile/i, phase.id);
    assert.ok(phase.explanation && phase.how?.length >= 2, phase.id + ': spiegazione del meccanismo');
  }
});
test('il dettaglio mostra prima il funzionamento e poi l’esempio con riscontri documentati', () => {
  const html=fs.readFileSync(path.resolve(__dirname,'../Architettura_per_il_relatore.html'),'utf8');
  const dom=new JSDOM(html,{runScripts:'dangerously',url:'file:///tesi.html#piano?esempio=melanoma'});
  try {
    const d=dom.window.document;const graph=d.querySelector('.diagram-section');const example=d.querySelector('.example-panel');
    assert.ok(graph.compareDocumentPosition(example) & dom.window.Node.DOCUMENT_POSITION_FOLLOWING);
    assert.doesNotMatch(graph.querySelector('svg').textContent,/Controllare il passaggio|Segnalare un limite|INFORMAZIONI|ELABORAZIONE|RISULTATO/);
    assert.match(d.getElementById('main').textContent,/UNMAPPED/);
    assert.match(d.getElementById('main').textContent,/DOID:1909/);
    const proof=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../verifica/esempi.json'),'utf8'));
    assert.equal(proof.entityResolution.intervention.status,'UNMAPPED');
    assert.equal(proof.operationalGateExample.status,'AMBIGUOUS');
  } finally {dom.window.close();}
});
test('lo zoom modifica la dimensione effettiva anche per diagrammi più larghi della pagina', () => {
  const html=fs.readFileSync(path.resolve(__dirname,'../Architettura_per_il_relatore.html'),'utf8');
  for (const [route,selector,label] of [['piano','.diagram-inner','Ingrandisci la figura'],['macro-recupero','.macro-diagram-inner','Ingrandisci il diagramma']]) {
    const dom=new JSDOM(html,{runScripts:'dangerously',url:'file:///tesi.html#'+route});
    try {
      const d=dom.window.document,inner=d.querySelector(selector);const before=parseFloat(inner.style.width);
      d.querySelector('[aria-label="'+label+'"]').click();
      assert.ok(parseFloat(inner.style.width)>before,route);
      assert.equal(inner.style.minWidth,'0px');
    } finally {dom.window.close();}
  }
});
test('Entity Resolution spiega gene-variante, contesto di malattia e nomi non risolti', () => {
  const phase = data.phases.find(p => p.id === 'piano');
  const text = JSON.stringify(phase);
  assert.match(text, /NCBIGene:673/);
  assert.match(text, /CIViCVariant:563/);
  assert.match(text, /UNMAPPED/);
  assert.match(text, /metastatic/);
  assert.ok(phase.flow.edges.length >= 7);
});
