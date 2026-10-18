'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const macros = require('../macro-data.js');
const lessons = require('../detail-lessons.cjs');
const paths = require('../path-views.js');

function checkBranches(graph) {
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  for (const id of ['struttura', 'contenuto', 'alternativa', 'esatto']) assert.ok(nodes.has(id), id);
  assert.match(nodes.get('struttura').title, /identità|Identità/);
  assert.match(nodes.get('contenuto').title, /citazioni|Citazioni/);
  assert.match(nodes.get('esatto').title, /esatto/);
  assert.ok(graph.edges.some(edge => edge[0] === 'contenuto' && edge[1] === 'alternativa'));
  assert.ok(graph.edges.some(edge => edge[0] === 'struttura' && edge[1] === 'alternativa'));
  assert.ok(graph.edges.some(edge => edge[0] === 'alternativa' && edge[1] === 'esatto'));
}

test('presentazione distingue controlli sulla prosa e confronto esatto del ripiego', () => {
  const item = macros.items.find(item => item.id === 'macro-presentazione');
  checkBranches(item.flow);
  checkBranches(lessons.fedelta.flow);
  for (const example of ['melanoma', 'studio', 'diagnostica']) checkBranches(paths.macro(item, example).flow);
  assert.match(JSON.stringify(item.clarification), /Prima del dossier/);
  assert.match(JSON.stringify(item.clarification), /Dopo il dossier/);
});
