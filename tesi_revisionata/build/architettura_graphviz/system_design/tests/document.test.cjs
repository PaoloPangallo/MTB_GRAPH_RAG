'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const frontendRequire = createRequire(path.resolve(__dirname, '../../../../../mtb-graphrag/frontend/package.json'));
const { JSDOM, VirtualConsole } = frontendRequire('jsdom');
const base = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(base, 'System_design_architettura.html'), 'utf8');
const data = require('../data.js');

function open(hash = '') {
  const errors = [];
  const console = new VirtualConsole();
  console.on('jsdomError', error => errors.push(error));
  const dom = new JSDOM(source, { runScripts: 'dangerously', url: 'file:///document.html' + hash, pretendToBeVisual: true, virtualConsole: console });
  dom.window.scrollTo = () => {};
  dom.window.print = () => {};
  return { dom, window: dom.window, document: dom.window.document, errors };
}
async function settle() { await new Promise(resolve => setTimeout(resolve, 12)); }
async function go(window, hash) { window.location.hash = hash; await settle(); }

test('il file autonomo apre tutte le fasi e i quattro pannelli senza errori DOM', async () => {
  const { dom, document, window, errors } = open();
  try {
    assert.equal(document.querySelectorAll('.map-node').length, 18);
    for (const phase of data.phases) {
      for (const example of ['melanoma', 'studio', 'diagnostica']) {
        for (const tab of ['sintesi', 'contratti', 'controlli', 'codice']) {
          await go(window, `#${phase.id}?esempio=${example}&vista=${tab}`);
          assert.equal(document.querySelector('h1').textContent, phase.title);
          assert.equal(document.querySelector('[aria-selected="true"]').id, 'tab-' + tab);
          if (tab === 'sintesi') assert.ok(document.querySelector('.diagram-inner svg'));
          if (tab === 'codice') assert.ok(document.querySelector('.example-provenance'));
        }
      }
    }
    assert.deepEqual(errors.map(error => error.message), []);
  } finally { dom.window.close(); }
});

test('il cambio esempio mostra il percorso senza documento e mantiene la fase aperta', async () => {
  const { dom, document, window } = open('#reader?esempio=melanoma&vista=sintesi');
  try {
    assert.ok(document.getElementById('node-lettore'));
    const example = document.getElementById('example');
    example.value = 'diagnostica'; example.dispatchEvent(new window.Event('change')); await settle();
    assert.equal(document.querySelector('h1').textContent, 'Leggere la fonte e descrivere ciò che dice');
    assert.ok(document.getElementById('node-assenza'));
    const node = document.getElementById('node-origine');
    node.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    assert.match(document.querySelector('.component-inspector').textContent, /non simula la lettura/);
  } finally { dom.window.close(); }
});

test('ricerca, tastiera e stampa completa restano operativi', async () => {
  const { dom, document, window } = open('#selezione?esempio=melanoma&vista=sintesi');
  try {
    const search = document.getElementById('search');
    search.value = 'non-esiste-zz'; search.dispatchEvent(new window.Event('input'));
    assert.equal(document.getElementById('no-results').hidden, false);
    assert.doesNotMatch(document.getElementById('no-results').textContent, /\bstage\b/i);
    search.value = 'sufficienza'; search.dispatchEvent(new window.Event('input'));
    assert.equal(document.querySelectorAll('.nav-phase').length, 1);
    document.getElementById('tab-sintesi').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    await settle();
    assert.equal(document.querySelector('[aria-selected="true"]').id, 'tab-contratti');
    assert.equal(document.activeElement.id, 'tab-contratti');
    window.dispatchEvent(new window.Event('beforeprint'));
    assert.equal(document.querySelectorAll('.print-phase').length, 19);
    assert.equal(document.querySelectorAll('.print-phase svg').length, 18);
  } finally { dom.window.close(); }
});

test('Vai al contenuto conserva passaggio ed esempio selezionati', async () => {
  const { dom, document, window } = open('#reader?esempio=studio&vista=contratti');
  try {
    document.querySelector('.skip-link').click(); await settle();
    assert.equal(document.querySelector('h1').textContent, 'Leggere la fonte e descrivere ciò che dice');
    assert.equal(document.getElementById('example').value, 'studio');
    assert.equal(document.activeElement.id, 'main');
  } finally { dom.window.close(); }
});

test('Escape chiude il menu e restituisce il focus al comando Fasi', () => {
  const { dom, document, window } = open();
  try {
    const menu = document.getElementById('menu');
    menu.click();
    assert.equal(document.activeElement.id, 'search');
    document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    assert.equal(menu.getAttribute('aria-expanded'), 'false');
    assert.equal(document.activeElement.id, 'menu');
  } finally { dom.window.close(); }
});
