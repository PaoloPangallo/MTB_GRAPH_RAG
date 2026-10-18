'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const {JSDOM}=createRequire(path.resolve(__dirname,'../../../../../mtb-graphrag/frontend/package.json'))('jsdom');
const base=path.resolve(__dirname,'..');
test('audit leggibile offline, collegamenti interni e valori ricalcolati',()=>{
  const html=fs.readFileSync(path.join(base,'Audit_GCA_per_il_relatore.html'),'utf8');
  const d=new JSDOM(html).window.document;
  assert.equal(d.documentElement.lang,'it');
  assert.equal(d.querySelectorAll('script[src],link[rel=stylesheet],iframe').length,0);
  assert.ok(d.querySelector('figure svg'));
  for(const link of d.querySelectorAll('a[href^="#"]'))assert.ok(d.querySelector(link.getAttribute('href')));
  assert.equal(d.querySelectorAll('section').length,12);
  assert.match(d.body.textContent,/46\.974/);
  assert.match(d.body.textContent,/5\.002/);
  assert.match(d.body.textContent,/2 valori distinti/);
  assert.match(d.getElementById('integrita').textContent,/DOI collocate nel campo PMID/);
  assert.match(d.getElementById('metodo').textContent,/perimetro dell’audit è la struttura e la coerenza interna/);
  const ids=[...d.querySelectorAll('[id]')].map(el=>el.id);
  assert.equal(new Set(ids).size,ids.length);
});
test('le edizioni dell’architettura aprono la pagina dedicata all’audit',()=>{
  for(const name of ['Architettura_per_il_relatore.html','Architettura_per_il_relatore_breve.html']){
    const d=new JSDOM(fs.readFileSync(path.join(base,name),'utf8')).window.document;
    assert.ok(d.querySelector('a[href="Audit_GCA_per_il_relatore.html"]'));
  }
});
test('la sezione paper e NCT presenta due audit con denominatori espliciti',()=>{
  const d=new JSDOM(fs.readFileSync(path.join(base,'Audit_paper_NCT_per_il_relatore.html'),'utf8')).window.document;
  assert.equal(d.querySelectorAll('script[src],link[rel=stylesheet],iframe').length,0);
  assert.ok(d.getElementById('paper'));assert.ok(d.getElementById('nct'));
  for(const link of d.querySelectorAll('a[href^="#"]'))assert.ok(d.querySelector(link.getAttribute('href')));
  assert.match(d.getElementById('perimetro').textContent,/2\.222 PMID numerici distinti/);
  assert.match(d.getElementById('perimetro').textContent,/4\.136 codici NCT distinti/);
  assert.match(d.getElementById('nct').textContent,/hasResults/);
  assert.match(d.getElementById('nct').textContent,/snapshot/);
  assert.ok(d.querySelector('a[href="verifica/paper-audit-inventario.csv"]'));
  assert.ok(d.querySelector('a[href="verifica/nct-audit-inventario.csv"]'));
  const gca=new JSDOM(fs.readFileSync(path.join(base,'Audit_GCA_per_il_relatore.html'),'utf8')).window.document;
  assert.ok(gca.querySelector('a[href="Audit_paper_NCT_per_il_relatore.html"]'));
});
test('audit source unit separa ricostruzione, indice storico e selezione',()=>{
  const d=new JSDOM(fs.readFileSync(path.join(base,'Audit_source_unit_per_il_relatore.html'),'utf8')).window.document;
  assert.equal(d.querySelectorAll('script[src],link[rel=stylesheet],iframe').length,0);
  assert.match(d.getElementById('perimetro-su').textContent,/Indice storico dei locatori/);
  assert.match(d.getElementById('uso-su').textContent,/BM25 strutturale e MedCPT/);
  assert.match(d.getElementById('locatori-su').textContent,/paragrafo full text/);
  assert.match(d.body.textContent,/255\.051/);
  for(const link of d.querySelectorAll('a[href^="#"]'))assert.ok(d.querySelector(link.getAttribute('href')));
  assert.ok(d.querySelector('a[href="verifica/sourceunit-inventario.csv.gz"]'));
  for(const name of ['Architettura_per_il_relatore.html','Architettura_per_il_relatore_breve.html']){
    const main=new JSDOM(fs.readFileSync(path.join(base,name),'utf8')).window.document;
    const button=main.querySelector('a[href="Audit_source_unit_per_il_relatore.html"]');
    assert.ok(button);assert.equal(button.previousElementSibling.getAttribute('href'),'Audit_paper_NCT_per_il_relatore.html');
  }
});
