'use strict';
const fs=require('node:fs');
const path=require('node:path');
const macros=require('./macro-data.js');
const paths=require('./path-views.js');
const data=require('./data.js');
const {dot}=require('./macro-build.cjs');
const base=__dirname;
const folder=path.join(base,'figure/percorsi');fs.mkdirSync(folder,{recursive:true});
const entries=paths.entries(data,macros);
for(const entry of entries){
  const source=dot(entry.flow,entry.key.startsWith('breve-')?'':entry.title);
  fs.writeFileSync(path.join(folder,entry.key+'.dot'),entry.key.startsWith('macro-')||entry.key.startsWith('breve-')?source:source.replace(/id="macro-node-/g,'id="node-'));
}
fs.writeFileSync(path.join(base,'verifica/path-assets.json'),JSON.stringify(entries.map(({key,title})=>({key,title})),null,2));
const briefs=Object.fromEntries(Object.keys(paths.profiles).map(example=>[example,{
  label:paths.profiles[example].label,
  pages:macros.items.map(item=>{
    const view=paths.brief(item,example);
    return {title:item.title,lead:item.lead,clarification:item.clarification,points:view.points,key:view.assetKey,step:macros.exampleStep(item.id,example)};
  })
}]));
fs.writeFileSync(path.join(base,'verifica/brief-content.json'),JSON.stringify(briefs,null,2));
console.log(entries.length+' figure coerenti con i percorsi; contenuti della versione breve preparati.');
