'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const macros = require('./macro-data.js');
const base = __dirname;
const target = path.join(base, 'figure/macrofasi');
const sourceRoot = path.resolve(base, '../../../../mtb-graphrag');
const q = JSON.stringify;
const palette = { dato: '#EAF0F5', codice: '#E8F4F0', controllo: '#F0EBF6', risultato: '#E6F3EC', modello: '#FBF1DD', encoder: '#FBF1DD', limite: '#F8EEE8' };
function dot(graph, title) {
  const lines = ['digraph macro {',
    'graph [rankdir=TB, bgcolor="white", pad="0.22", nodesep="0.30", ranksep="0.40", splines=polyline, outputorder=edgesfirst];',
    'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=17, fontcolor="#17343F", color="#AFC4C8", penwidth=1, margin="0.20,0.15"];',
    'edge [color="#617E87", fontname="Arial", fontcolor="#365661", fontsize=13, arrowsize=0.7];'];
  lines.push(`graph [label=${q(title)}, labelloc=t, fontname="Arial", fontsize=22, fontcolor="#17343F", labeljust=c];`);
  for (const n of graph.nodes) lines.push(`${q(n.id)} [id=${q('macro-node-' + n.id)}, label=${q(n.title)}, shape=${q(n.shape || 'box')}, fillcolor=${q(palette[n.kind] || palette.codice)}, tooltip=${q(n.detail)}];`);
  for (const [from, to, label, style] of graph.edges) lines.push(`${q(from)} -> ${q(to)} [label=${q(label)}, style=${q(style || 'solid')}];`);
  for (const rank of graph.ranks || []) lines.push(`{rank=same; ${rank.map(q).join('; ')};}`);
  return lines.concat('}').join('\n');
}
module.exports={dot};
if(require.main===module){
fs.mkdirSync(target, { recursive: true });
for (const item of [...macros.items, { id: 'rrf', title: 'Reciprocal Rank Fusion (RRF)', flow: macros.rrfFlow }]) {
  const graph=item.id==='rrf'?item.flow:require('./path-views.js').macro(item,'melanoma').flow;
  fs.writeFileSync(path.join(target, item.id + '.dot'), dot(graph, item.title));
}
const references = macros.sources.map(([file, symbol]) => {
  const bytes = fs.readFileSync(path.join(sourceRoot, file));
  const lines = bytes.toString('utf8').split(/\r?\n/);
  const line = lines.findIndex(value => value.includes(symbol));
  if (line < 0) throw new Error(`Missing macro reference ${file}: ${symbol}`);
  return { file, symbol, line: line + 1, sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
});
fs.writeFileSync(path.join(base, 'verifica/macrofasi-sources.json'), JSON.stringify({ references, rrf: macros.rrf, defaultDocumentaryProfile: 'legacy', optionalDocumentaryProfile: 'focused-v1' }, null, 2));
console.log('Sette sorgenti Graphviz; riferimenti alle implementazioni verificati.');
}
