/* Rebuild the local document from verified source references and Graphviz SVGs. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const data = require('./data.js');
const lessons = require('./detail-lessons.cjs');
for (const phase of data.phases) Object.assign(phase, lessons[phase.id], { summary: lessons[phase.id].explanation });
const base = __dirname;
const sourceRoot = path.resolve(base, '../../../../mtb-graphrag');
const figures = path.join(base, 'figure');
const verification = path.join(base, 'verifica');
fs.mkdirSync(figures, { recursive: true });
fs.mkdirSync(verification, { recursive: true });
const q = value => JSON.stringify(value);
const safeJSON = value => JSON.stringify(value).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
const colors = { dato: '#EAF0F5', codice: '#E8F4F0', controllo: '#F0EBF6', risultato: '#E6F3EC', modello: '#FBF1DD', encoder: '#FBF1DD', limite: '#F8EEE8' };
function wrap(value, maximum = 24) {
  const lines = [''];
  for (const word of value.split(/\s+/)) {
    if (lines.at(-1).length + word.length > maximum && lines.at(-1)) lines.push(word);
    else lines[lines.length - 1] += (lines.at(-1) ? ' ' : '') + word;
  }
  return lines.join('\n');
}
function dot(flow, title) {
  const lines = ['digraph phase {',
    `graph [rankdir=${q(flow.direction || 'TB')}, bgcolor="white", pad="0.25", nodesep="0.35", ranksep="0.45", splines=polyline, label=${q(title)}, labelloc=t, fontname="Arial", fontsize=21, fontcolor="#17343F"];`,
    'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=16, fontcolor="#17343F", color="#B7C9CF", penwidth=1, margin="0.18,0.14"];',
    'edge [color="#718895", fontname="Arial", fontcolor="#365661", fontsize=12, arrowsize=0.65];'];
  for (const node of flow.nodes) lines.push(`${q(node.id)} [id=${q('node-' + node.id)}, shape=${q(node.shape || 'box')}, label=${q(node.title.split('\n').map(line => wrap(line, 42)).join('\n'))}, fillcolor=${q(colors[node.kind] || colors.codice)}, tooltip=${q(node.detail)}];`);
  for (const [from, to, label, style] of flow.edges) lines.push(`${q(from)} -> ${q(to)} [label=${q(wrap(label, 28))}, style=${q(style || 'solid')}];`);
  for (const rank of flow.ranks || []) lines.push(`{rank=same; ${rank.map(value => q(value)).join('; ')};}`);
  return lines.concat('}').join('\n');
}

if (!process.argv.includes('--assemble')) {
  const sourceMap = new Map();
  const refs = {};
  for (const phase of data.phases) {
    refs[phase.id] = phase.refs.map(ref => {
      const file = path.resolve(sourceRoot, ref.file);
      const relative = path.relative(sourceRoot, file);
      if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Reference outside source root');
      const bytes = fs.readFileSync(file);
      const lines = bytes.toString('utf8').split(/\r?\n/);
      const escaped = ref.symbol.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const pattern = new RegExp('^\\s*(?:(?:def|class)\\s+)?' + escaped + '\\b');
      const index = lines.findIndex(line => ref.anchor ? line.includes(ref.anchor) : pattern.test(line));
      if (index < 0) throw new Error(`Reference not found: ${ref.file} / ${ref.symbol}`);
      const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
      sourceMap.set(ref.file, { file: ref.file, sha256 });
      return { ...ref, line: index + 1, excerpt: lines.slice(index, index + 15).join('\n'), sha256 };
    });
    fs.writeFileSync(path.join(figures, `${phase.id}.dot`), dot(phase.flow, phase.title));
    if (phase.focusedFlow) fs.writeFileSync(path.join(figures, `${phase.id}-focused.dot`), dot(phase.focusedFlow, phase.title));
  }
  if (data.graphOnlyFlow) fs.writeFileSync(path.join(figures, 'solo-grafo.dot'), dot(data.graphOnlyFlow, 'Relazioni del solo Knowledge Graph'));
  const contract = fs.readFileSync(path.join(sourceRoot, 'backend/research_pipeline/contracts.py'), 'utf8');
  const expected = [...contract.matchAll(/\("(stage_[^"]+)",\s*"[A-Z_]+"\)/g)].map(match => match[1]);
  const actual = data.phases.flatMap(phase => phase.stageIds);
  if (JSON.stringify(expected) !== JSON.stringify(actual)) throw new Error('The documented stage sequence differs from contracts.py');
  const manifest = { verifiedOn: '2026-10-17', method: 'static_source_review', liveRunExecuted: false, stages: actual, sources: [...sourceMap.values()], references: refs };
  fs.writeFileSync(path.join(verification, 'sources.json'), JSON.stringify(manifest, null, 2));
  console.log(`${data.phases.length} fasi; ${actual.length} stage; ${sourceMap.size} file sorgente verificati. DOT pronti per Graphviz.`);
} else {
  const manifest = JSON.parse(fs.readFileSync(path.join(verification, 'sources.json'), 'utf8'));
  for (const ref of manifest.sources) {
    const sha256 = crypto.createHash('sha256').update(fs.readFileSync(path.join(sourceRoot, ref.file))).digest('hex');
    if (sha256 !== ref.sha256) throw new Error(`Source changed after verification: ${ref.file}`);
  }
  const svgs = {};
  const dots = {};
  const pdfs = {};
  for (const file of [...data.phases.map(phase => phase.id + '.dot'), ...(data.graphOnlyFlow ? ['solo-grafo.dot'] : [])]) {
    const key = path.basename(file, '.dot');
    dots[key] = fs.readFileSync(path.join(figures, file), 'utf8');
    svgs[key] = fs.readFileSync(path.join(figures, key + '.svg'), 'utf8').replace(/<\?xml[\s\S]*?\?>/, '').replace(/<!DOCTYPE[\s\S]*?>/, '');
    pdfs[key] = fs.readFileSync(path.join(figures, key + '.pdf')).toString('base64');
  }
  for (const key of [...require('./macro-data.js').items.map(item => item.id), 'rrf']) {
    const prefix = path.join(figures, 'macrofasi', key);
    dots[key] = fs.readFileSync(prefix + '.dot', 'utf8');
    svgs[key] = fs.readFileSync(prefix + '.svg', 'utf8').replace(/<\?xml[\s\S]*?\?>/, '').replace(/<!DOCTYPE[\s\S]*?>/, '');
    pdfs[key] = fs.readFileSync(prefix + '.pdf').toString('base64');
  }
  for(const {key} of JSON.parse(fs.readFileSync(path.join(verification,'path-assets.json'),'utf8'))){
    const prefix=path.join(figures,'percorsi',key);
    dots[key]=fs.readFileSync(prefix+'.dot','utf8');
    svgs[key]=fs.readFileSync(prefix+'.svg','utf8').replace(/<\?xml[\s\S]*?\?>/,'').replace(/<!DOCTYPE[\s\S]*?>/,'');
    pdfs[key]=fs.readFileSync(prefix+'.pdf').toString('base64');
  }
  for(const example of ['melanoma','studio','diagnostica'])pdfs['breve--'+example]=fs.readFileSync(path.resolve(base,'../../../../output/pdf/architettura/Relatore_breve_'+example+'.pdf')).toString('base64');
  const macroManifest = JSON.parse(fs.readFileSync(path.join(verification, 'macrofasi-sources.json'), 'utf8'));
  for (const ref of macroManifest.references) {
    const current = crypto.createHash('sha256').update(fs.readFileSync(path.join(sourceRoot, ref.file))).digest('hex');
    if (current !== ref.sha256) throw new Error(`Macro source changed: ${ref.file}`);
  }
  const assets = 'globalThis.ArchitectureAssets = ' + safeJSON({ svgs, dots, pdfs, verifiedOn: manifest.verifiedOn }) + ';\n';
  fs.writeFileSync(path.join(base, 'assets.js'), assets);
  const publicData = { ...data, macros: require('./macro-data.js').items, phases: data.phases.map(({ refs, stageIds, technicalNumber, ...phase }) => phase) };
  const publicScript = 'globalThis.ArchitectureData = ' + safeJSON(publicData) + ';\n';
  fs.writeFileSync(path.join(base, 'public-data.js'), publicScript);
  const html = fs.readFileSync(path.join(base, 'index.html'), 'utf8');
  const css = fs.readFileSync(path.join(base, 'styles.css'), 'utf8');
  const scripts = ['public-data.js', 'macro-data.js', 'path-views.js', 'view-model.js', 'assets.js', 'examples.js', 'journey.js', 'macro-ui.js', 'app.js'].map(file => fs.readFileSync(path.join(base, file), 'utf8'));
  const single = html.replace('<link rel="stylesheet" href="styles.css">', '<style>\n' + css + '\n</style>')
    .replace(/<script src="(?:public-data|macro-data|path-views|view-model|assets|examples|journey|macro-ui|app)\.js"><\/script>/g, '')
    .replace('</body>', scripts.map(script => '<script>\n' + script.replace(/<\/script/gi, '<\\/script') + '\n</script>').join('\n') + '\n</body>');
  fs.writeFileSync(path.join(base, 'System_design_architettura.html'), single);
  fs.writeFileSync(path.join(base, 'Architettura_per_il_relatore.html'), single);
  fs.writeFileSync(path.join(base,'Architettura_per_il_relatore_breve.html'),single.replace('<body>','<body data-edition="breve">'));
  console.log(`Documento autonomo creato: ${Buffer.byteLength(single)} byte; ${Object.keys(svgs).length} diagrammi SVG incorporati.`);
}
