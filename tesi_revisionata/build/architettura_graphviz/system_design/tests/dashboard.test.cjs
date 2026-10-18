'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { JSDOM } = createRequire(path.resolve(__dirname, '../../../../../mtb-graphrag/frontend/package.json'))('jsdom');
const base = path.resolve(__dirname, '..');

test('dashboard raccoglie gli accessi e lascia una barra essenziale', () => {
  const dom = new JSDOM(fs.readFileSync(path.join(base, 'index.html'), 'utf8'));
  const d = dom.window.document;
  assert.equal(d.querySelectorAll('.top-actions a').length, 1);
  const dashboard = d.getElementById('dashboard');
  assert.ok(dashboard);
  assert.equal(dashboard.querySelectorAll('.dashboard-path a').length, 6);
  assert.equal(dashboard.querySelectorAll('.dashboard-group').length, 2);
  assert.ok(dashboard.querySelector('#download-brief'));
  for (const file of ['Audit_GCA_per_il_relatore.html', 'Audit_paper_NCT_per_il_relatore.html',
    'Audit_source_unit_per_il_relatore.html', 'Prompt_di_sistema_per_il_relatore.html',
    'Prove_narratore_per_il_relatore.html', 'Architettura_per_il_relatore_breve.html']) {
    const link = dashboard.querySelector('a[href="' + file + '"]');
    assert.ok(link, file);
    assert.ok(link.querySelector('p'), 'descrizione per ' + file);
    assert.ok(fs.existsSync(path.join(base, file)));
  }
  dom.window.close();
});

test('la dashboard lascia spazio alle fasi e ritorna dalla navigazione', async () => {
  const dom = new JSDOM(fs.readFileSync(path.join(base, 'Architettura_per_il_relatore.html'), 'utf8'),
    { runScripts: 'dangerously', url: 'file:///Architettura_per_il_relatore.html' });
  dom.window.scrollTo = () => {};
  try {
    const d = dom.window.document;
    assert.equal(d.getElementById('dashboard').hidden, false);
    d.getElementById('example').value = 'diagnostica';
    d.getElementById('example').dispatchEvent(new dom.window.Event('change'));
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.match(d.querySelector('.dashboard-feature').getAttribute('href'), /esempio=diagnostica/);
    assert.ok(d.querySelector('#content > details.dashboard-map'));
    dom.window.location.hash = '#macro-verifiche?esempio=studio';
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(d.getElementById('dashboard').hidden, true);
    assert.match(d.querySelector('#content h1').textContent, /Verifiche/);
    dom.window.location.hash = '#panoramica';
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(d.getElementById('dashboard').hidden, false);
  } finally { dom.window.close(); }
});

test('la lettura breve conserva un accesso diretto al PDF', () => {
  const dom = new JSDOM(fs.readFileSync(path.join(base, 'Architettura_per_il_relatore_breve.html'), 'utf8'),
    { runScripts: 'dangerously' });
  try {
    assert.equal(dom.window.document.getElementById('dashboard').hidden, true);
    assert.ok(dom.window.document.querySelector('#content .brief-download'));
  } finally { dom.window.close(); }
});
