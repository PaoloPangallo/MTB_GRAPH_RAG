'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const localRequire = createRequire(path.resolve(__dirname, '../../../../../mtb-graphrag/frontend/package.json'));
const { JSDOM, VirtualConsole } = localRequire('jsdom');
const html = fs.readFileSync(path.resolve(__dirname, '../System_design_architettura.html'), 'utf8');
const technical = /\b(?:CleanGraphData|SourceUnit|CaseContext|RunStore|PipelineRun|SelectionIndex|KG_ONLY|PAPER_EVIDENCE|runtime|snapshot|ledger|SHA-256)\b/i;
function open(hash = '') {
  const errors = [];
  const console = new VirtualConsole();
  console.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, url: 'file:///presentazione.html' + hash, virtualConsole: console });
  dom.window.scrollTo = () => {};
  return { dom, window: dom.window, document: dom.window.document, errors };
}
const settle = () => new Promise(resolve => setTimeout(resolve, 12));

test('la panoramica parla al relatore, con esempi e senza sigle interne', () => {
  const { dom, document } = open();
  try {
    assert.ok(!technical.test(document.getElementById('main').textContent));
    assert.doesNotMatch(document.getElementById('main').textContent, /\b20\d{2}\b|E2E20|stage_\d|GCA4-/);
    assert.ok(document.getElementById('example'));
    assert.equal(document.getElementById('profile'), null);
    assert.match(document.body.textContent, /Architettura attuale/);
  } finally { dom.window.close(); }
});

test('tutte le fasi sono comprensibili e accompagnate da un esempio verificato', async () => {
  const data = require('../data.js');
  const { dom, document, window, errors } = open();
  try {
    for (const phase of data.phases) {
      for (const tab of ['sintesi', 'contratti', 'controlli', 'codice']) {
        window.location.hash = `#${phase.id}?esempio=melanoma&vista=${tab}`;
        await settle();
        assert.ok(!technical.test(document.getElementById('main').textContent), phase.id + ' / ' + tab);
        assert.doesNotMatch(document.getElementById('main').textContent, /\b20\d{2}\b|E2E20|stage_\d|GCA4-/, phase.id + ' / ' + tab);
        assert.ok(document.querySelector('.example-panel'), phase.id);
      }
    }
    assert.deepEqual(errors, []);
  } finally { dom.window.close(); }
});

test('gli esempi distinguono associazione, citazione e applicabilità', async () => {
  const { dom, document, window } = open('#validazione?esempio=melanoma&vista=codice');
  try {
    assert.match(document.getElementById('main').textContent, /28891408/);
    assert.match(document.getElementById('main').textContent, /stadio III/);
    assert.match(document.getElementById('main').textContent, /metastatico/);
    assert.match(document.getElementById('main').textContent, /sintetico/);
    assert.match(document.getElementById('main').textContent, /non.*(?:dimostra|attribuit|trasferibil)/i);
    window.location.hash = '#reader?esempio=diagnostica&vista=sintesi'; await settle();
    assert.match(document.querySelector('.example-panel').textContent, /non.*(?:lettura|pubblicazione|documento)/i);
  } finally { dom.window.close(); }
});

test('le prove degli esempi sono legate ai record reali e ai file archiviati', () => {
  const proof = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../verifica/esempi.json'), 'utf8'));
  assert.equal(proof.corpus.sha256, '4e197764dff17cb396c5026338f07e001c0573e37bec9fb0f8a32e652b9d7edd');
  assert.ok(proof.records.length >= 5);
  assert.equal(proof.execution.syntheticCase, true);
  assert.equal(proof.newExecutionPerformed, false);
  assert.ok(proof.paper.quoteAuthenticated);
  assert.equal(proof.paper.claimSupport, 'NO_SUPPORT');
});
