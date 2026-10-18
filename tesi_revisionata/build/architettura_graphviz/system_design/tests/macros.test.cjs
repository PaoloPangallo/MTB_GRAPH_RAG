'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { JSDOM } = createRequire(path.resolve(__dirname, '../../../../../mtb-graphrag/frontend/package.json'))('jsdom');
const html = () => fs.readFileSync(path.resolve(__dirname, '../Architettura_per_il_relatore.html'), 'utf8');
const ids = ['macro-caso', 'macro-recupero', 'macro-fonti', 'macro-verifiche', 'macro-dossier', 'macro-presentazione'];
const forbidden = /\b20\d{2}\b|E2E20|GCA4-|stage_\d|analisi archiviata|run_id|SHA-256/;
test('sei macrofasi principali e diciotto approfondimenti richiudibili', () => {
  const dom = new JSDOM(html(), { runScripts: 'dangerously' });
  try {
    const d = dom.window.document;
    assert.equal(d.querySelectorAll('.nav-macro').length, 6);
    assert.equal(d.querySelectorAll('details .nav-phase').length, 18);
    assert.equal(d.querySelectorAll('.system-step').length, 6);
    assert.doesNotMatch(d.getElementById('main').textContent, forbidden);
  } finally { dom.window.close(); }
});
test('l’esempio attraversa sei macrofasi con diagrammi specifici e PDF incorporati', () => {
  for (const example of ['melanoma', 'studio', 'diagnostica']) for (const id of ids) {
    const dom = new JSDOM(html(), { runScripts: 'dangerously', url: `file:///tesi.html#${id}?esempio=${example}` });
    try {
      const d = dom.window.document;
      assert.ok(d.querySelector('.macro-diagram svg'), `${id}/${example}`);
      assert.equal(d.querySelectorAll('.macro-example .journey-step').length, 3);
      assert.ok(d.querySelector('.download-pdf'));
      assert.doesNotMatch(d.getElementById('main').textContent, forbidden, id);
      assert.match(d.querySelector('.macro-example').textContent, /BRAF|V600K/);
    } finally { dom.window.close(); }
  }
});
test('RRF usa i ranghi da uno, k=60 e somma contributi senza media dei punteggi', () => {
  const macro = require('../macro-data.js');
  for (const row of macro.rrf.rows) {
    const score = (row.structure ? 1 / (60 + row.structure) : 0) + (row.medcpt ? 1 / (60 + row.medcpt) : 0);
    assert.ok(Math.abs(row.score - score) < 1e-12);
  }
  assert.deepEqual([...macro.rrf.rows].sort((a,b) => b.score - a.score).map(x => x.id), ['B','A','C','D']);
});
test('il cambio percorso conserva macrofase e focus da tastiera', async () => {
  const dom = new JSDOM(html(), { runScripts:'dangerously', pretendToBeVisual:true, url:'file:///tesi.html#macro-fonti?esempio=melanoma' });
  try {
    const d=dom.window.document;
    const button=d.querySelectorAll('.macro-paths button')[1];button.focus();button.click();
    await new Promise(resolve=>setTimeout(resolve,20));
    assert.match(dom.window.location.hash,/macro-fonti.*studio/);
    assert.equal(d.activeElement,d.querySelector('.macro-paths [aria-pressed="true"]'));
    assert.match(d.querySelector('.macro-example').textContent,/NCT02279004/);
  } finally {dom.window.close();}
});
test('stampa e asset offline includono macrofasi e PDF vettoriali scaricabili', () => {
  const dom=new JSDOM(html(),{runScripts:'dangerously'});
  try {
    dom.window.print=()=>{};dom.window.dispatchEvent(new dom.window.Event('beforeprint'));
    const d=dom.window.document;
    assert.equal(d.querySelectorAll('.print-macro').length,6);
    assert.equal(d.querySelectorAll('.print-phase').length,19);
    assert.doesNotMatch(d.getElementById('print-book').textContent,forbidden);
    for(const id of [...ids,'rrf']) {
      const bytes=Buffer.from(dom.window.ArchitectureAssets.pdfs[id],'base64');
      assert.equal(bytes.subarray(0,5).toString(),'%PDF-');
      assert.ok(bytes.equals(fs.readFileSync(path.resolve(__dirname,'../figure/macrofasi',id+'.pdf'))));
      assert.match(dom.window.ArchitectureAssets.svgs[id],/<text/);
    }
  } finally {dom.window.close();}
});
