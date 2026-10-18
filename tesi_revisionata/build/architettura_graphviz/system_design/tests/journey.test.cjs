'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { JSDOM } = createRequire(path.resolve(__dirname, '../../../../../mtb-graphrag/frontend/package.json'))('jsdom');
const html = () => fs.readFileSync(path.resolve(__dirname, '../Architettura_per_il_relatore.html'), 'utf8');
test('il risultato di ogni fase diventa esattamente l’ingresso della successiva', () => {
  const journey = require('../journey.js');
  for (const example of ['melanoma', 'studio', 'diagnostica']) {
    for (let index = 1; index < journey.order.length; index++) {
      const previous = journey.step(journey.order[index - 1], example, 'caso');
      const current = journey.step(journey.order[index], example, 'caso');
      assert.equal(current.input, previous.result, example + '/' + journey.order[index]);
    }
  }
});
test('la panoramica distingue preparazione, sei componenti, tre percorsi e coordinamento', () => {
  const dom = new JSDOM(html(), { runScripts: 'dangerously' });
  try {
    const doc = dom.window.document;
    assert.equal(doc.querySelectorAll('.system-step').length, 6);
    assert.equal(doc.querySelectorAll('.source-branch').length, 3);
    assert.ok(doc.querySelector('.system-preparation'));
    assert.ok(doc.querySelector('.system-coordination'));
    assert.doesNotMatch(doc.querySelector('.system-overview').textContent, /[A-Za-zÀ-ÿ]\?[A-Za-zÀ-ÿ]/);
  } finally { dom.window.close(); }
});
test('ogni fase e ogni ramo hanno un esempio progressivo anche in stampa', async () => {
  const phases = require('../data.js').phases;
  for (const example of ['melanoma', 'studio', 'diagnostica']) {
    const dom = new JSDOM(html(), { runScripts: 'dangerously', url: `file:///document.html#${phases[0].id}?esempio=${example}&vista=sintesi` });
    dom.window.scrollTo=()=>{};
    try {
    for (const phase of phases) {
      const nextHash=`#${phase.id}?esempio=${example}&vista=sintesi`;
      if(dom.window.location.hash!==nextHash){
        const changed=new Promise(resolve=>dom.window.addEventListener('hashchange',resolve,{once:true}));
        dom.window.location.hash=nextHash;
        await changed;
      }
        const doc = dom.window.document;
        assert.equal(doc.querySelector('#content h1').textContent,phase.title);
        assert.equal(doc.querySelectorAll('#content .journey-step').length, 3, `${example}/${phase.id}`);
        assert.ok(doc.querySelector('.journey-result').textContent.trim());
        if (phase.id === 'reader' && example === 'diagnostica') assert.match(doc.querySelector('.example-panel').textContent, /non.*lettura/i);
        if (phase.id === 'reader' && example === 'studio') assert.match(doc.querySelector('.example-panel').textContent, /senza.*generativa/i);
        if (phase.id === 'fedelta') {
          dom.window.print = () => {};
          dom.window.dispatchEvent(new dom.window.Event('beforeprint'));
          assert.equal(doc.querySelectorAll('#print-book .print-phase .journey-result').length, 18);
          assert.equal(doc.querySelectorAll('#print-book .print-macro').length, 6);
        }
    }
    } finally { dom.window.close(); }
  }
});
