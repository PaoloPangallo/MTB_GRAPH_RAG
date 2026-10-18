const test = require('node:test');
const assert = require('node:assert/strict');
const data = require('../data.js');
const state = require('../view-model.js');

test('un collegamento conserva passaggio, esempio e approfondimento', () => {
  const selected = { phase: 'selezione', example: 'studio', tab: 'contratti' };
  assert.deepEqual(state.parseLocation(state.serialize(selected), data), selected);
});

test('un indirizzo non riconosciuto apre una vista utilizzabile', () => {
  assert.deepEqual(state.parseLocation('#non-esiste?profilo=x&vista=y', data), {
    phase: 'panoramica', example: 'melanoma', tab: 'sintesi'
  });
});

test('la navigazione attraversa tutte le fasi senza perdere la fase 3b', () => {
  let current = 'panoramica';
  const visited = [];
  while (state.neighbors(current, data).next) {
    current = state.neighbors(current, data).next;
    assert.ok(!visited.includes(current), 'nessun ciclo nella navigazione');
    visited.push(current);
  }
  assert.deepEqual(visited, data.phases.map(phase => phase.id));
  assert.ok(visited.includes('ammissibilita'));
});

test('l’architettura attuale distingue pubblicazioni, registri e sola provenienza', () => {
  const reader = data.phases.find(phase => phase.id === 'reader');
  assert.ok(reader.flow.nodes.some(node => node.id === 'organizzare'));
  assert.ok(reader.flow.nodes.some(node => node.id === 'lettore'));
  assert.ok(reader.flow.nodes.some(node => node.id === 'origine'));
  assert.equal(reader.focusedFlow, undefined);
});

test('ogni fase dichiara contratti, esiti e riferimenti verificabili', () => {
  for (const phase of data.phases) {
    assert.ok(phase.input.length && phase.output.length, phase.id);
    assert.ok(phase.controls.length && phase.failures.length, phase.id);
    assert.ok(phase.refs.length, phase.id);
    for (const flow of [phase.flow, phase.focusedFlow].filter(Boolean)) {
      const ids = new Set(flow.nodes.map(node => node.id));
      assert.equal(ids.size, flow.nodes.length, phase.id);
      for (const edge of flow.edges) {
        assert.ok(ids.has(edge[0]) && ids.has(edge[1]), `${phase.id}: arco valido`);
      }
    }
  }
});

test('la ricerca restituisce il gate e gestisce una ricerca senza risultati', () => {
  assert.ok(state.searchPhases('sufficienza', data).some(phase => phase.id === 'ammissibilita'));
  assert.deepEqual(state.searchPhases('zzzzinesistente', data), []);
});
