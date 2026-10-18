'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const {JSDOM}=createRequire(path.resolve(__dirname,'../../../../../mtb-graphrag/frontend/package.json'))('jsdom');
const html=()=>fs.readFileSync(path.resolve(__dirname,'../Architettura_per_il_relatore.html'),'utf8');
test('ogni macrofase segue la fonte selezionata anche nella figura',()=>{
  for(const example of ['studio','diagnostica']) for(const macro of ['recupero','fonti','verifiche','dossier','presentazione']){
    const dom=new JSDOM(html(),{runScripts:'dangerously',url:`file:///tesi.html#macro-${macro}?esempio=${example}`});
    try{
      const graph=dom.window.document.querySelector('.macro-diagram svg').textContent;
      assert.doesNotMatch(graph,/28891408|adiuvante|stadio III|V600E/,`${example}/${macro}`);
      assert.match(graph,example==='studio'?/NCT02279004/:/FoundationOne/);
    }finally{dom.window.close();}
  }
});
test('la vista principale delle verifiche evita i nomi interni e mostra tre momenti',()=>{
  const dom=new JSDOM(html(),{runScripts:'dangerously',url:'file:///tesi.html#macro-verifiche?esempio=melanoma'});
  try{
    const d=dom.window.document;
    const graph=d.querySelector('.macro-diagram svg').textContent;
    assert.doesNotMatch(graph,/EVIDENCE_DRUG|PASS|NO_SUPPORT/);
    assert.match(graph,/Autenticazione/);assert.match(graph,/Controlli sulla relazione/);assert.match(graph,/Decisione/);
    assert.ok(d.querySelector('.verification-deep'));
  }finally{dom.window.close();}
});
test('la stampa breve contiene sei macrofasi e nessun approfondimento',()=>{
  const dom=new JSDOM(fs.readFileSync(path.resolve(__dirname,'../Architettura_per_il_relatore_breve.html'),'utf8'),{runScripts:'dangerously'});
  try{
    const d=dom.window.document;dom.window.print=()=>{};
    assert.equal(d.getElementById('print-brief'),null);
    assert.equal(d.getElementById('print'),null);
    dom.window.dispatchEvent(new dom.window.Event('beforeprint'));
    assert.equal(d.querySelectorAll('#print-book .print-macro').length,6);
    assert.equal(d.querySelectorAll('#print-book .print-phase').length,0);
  }finally{dom.window.close();}
});

test('gli approfondimenti alternativi conservano fonte ed esito del percorso',()=>{
  globalThis.ArchitectureMacros=require('../macro-data.js');
  const views=require('../path-views.js'), data=require('../data.js');
  for(const example of ['studio','diagnostica'])for(const phase of data.phases){
    const view=views.detail(phase,example);
    if(!view.assetKey.includes('--'))continue;
    const graph=JSON.stringify(view.flow);
    assert.doesNotMatch(graph,/28891408|stage III|stadio III|adiuvante/);
    assert.match(graph,example==='studio'?/NCT02279004/:/FoundationOne/);
  }
  assert.match(JSON.stringify(views.verificationFlow('studio')),/fatti strutturati, nessuna citazione Reader/);
});

test('la pagina breve autonoma mostra sei macrofasi',()=>{
  const brief=fs.readFileSync(path.resolve(__dirname,'../Architettura_per_il_relatore_breve.html'),'utf8');
  const dom=new JSDOM(brief,{runScripts:'dangerously',url:'file:///breve.html#macro-caso?esempio=studio'});
  try{assert.equal(dom.window.document.querySelectorAll('main .print-macro').length,6);}finally{dom.window.close();}
});

test('i chiarimenti distinguono identità, confronto semantico e fedeltà deterministica',()=>{
  const macros=require('../macro-data.js');
  const notes=id=>macros.items.find(item=>item.id===id).clarification;
  assert.match(JSON.stringify(notes('macro-recupero')),/valore originale|Originale/);
  assert.match(JSON.stringify(notes('macro-verifiche')),/solo per le relazioni evidenza–farmaco/);
  assert.match(JSON.stringify(notes('macro-verifiche')),/senza il verdetto del Reader/);
  assert.match(JSON.stringify(notes('macro-presentazione')),/confronto esatto/);
  assert.match(JSON.stringify(notes('macro-presentazione')),/regole deterministiche/);
  assert.match(JSON.stringify(notes('macro-presentazione')),/limite di verifica semantica/);
  const dom=new JSDOM(html(),{runScripts:'dangerously',url:'file:///tesi.html#macro-presentazione?esempio=studio'});
  try{
    const d=dom.window.document;
    assert.match(d.querySelector('.macro-clarification').textContent,/Il dossier è già costruito e rimane il riferimento/);
    assert.match(d.querySelector('.macro-clarification').textContent,/Ogni osservazione conservata deve avere una spiegazione/);
    const graph=d.querySelector('.macro-diagram svg').textContent;
    assert.match(graph,/Presentazione accettata/);assert.match(graph,/testo respinto/i);
    assert.match(graph,/confronto esatto/);assert.match(graph,/ripiego verificato/);
    assert.doesNotMatch(graph,/28891408/);
  }finally{dom.window.close();}
});
