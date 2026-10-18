const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
function harness(){
  let p='en/zh-TW',handler;const pending=[],errors=[],loads=[];
  const word={id:1},exercise={available:true};
  const S={templates:{template_id:'default'},layout:{value:1},dirty:false,word,exercise};
  const nodes=new Map([['template',{value:'B'}],['version',{value:'draft'}]]);
  const c=vm.createContext({S,JSON,structuredClone,pair:()=>p,templateQuery:()=>p+'&template_id='+S.templates.template_id,
    $:id=>nodes.get(id),on:(id,event,fn)=>handler=fn,
    api:path=>new Promise((resolve,reject)=>pending.push({path,resolve,reject})),
    save:()=>new Promise((resolve,reject)=>pending.push({save:true,resolve,reject})),
    error:e=>errors.push(e.message),toast(){},fillTemplates:()=>nodes.get('template').value=S.templates.template_id,
    fillVersions(){},busy:()=>S.exercise=null,chooseLayout(){},render(){},loadExercise:async()=>loads.push(true)});
  const start=source.indexOf('async function changeTemplate(){');if(start>=0)vm.runInContext('let templateRequest=0;'+source.slice(start,source.indexOf("on('template','change'",start)),c);
  vm.runInContext(source.split('\n').find(l=>l.startsWith("on('template','change'")),c);
  return {S,pending,errors,loads,nodes,word,exercise,change:()=>handler(),pair:x=>p=x};
}
test('old template success after language switch cannot overwrite current templates',async()=>{
  const h=harness(),task=h.change();h.pair('en/fr');const fresh={template_id:'fr'};h.S.templates=fresh;h.pending[0].resolve({template_id:'B'});await task;
  assert.equal(h.S.templates,fresh);assert.equal(h.loads.length,0);
});
test('old template failure after language switch is ignored',async()=>{
  const h=harness(),task=h.change();h.pair('en/fr');h.S.templates={template_id:'fr'};h.pending[0].reject(new Error('old outage'));await task;assert.equal(h.errors.length,0);
});
test('autosave finishing after language switch never requests old template in new language',async()=>{
  const h=harness();h.S.dirty=true;const task=h.change();h.pair('en/fr');h.S.templates={template_id:'fr'};h.pending[0].resolve(true);
  await new Promise(r=>setImmediate(r));if(h.pending[1])h.pending[1].resolve({template_id:'B'});await task;assert.equal(h.pending.length,1);
});
test('current failure restores dropdown and keeps existing word/exercise',async()=>{
  const h=harness(),task=h.change();h.pending[0].reject(new Error('offline'));await task;
  assert.equal(h.nodes.get('template').value,'default');assert.equal(h.S.word,h.word);assert.equal(h.S.exercise,h.exercise);assert.equal(h.errors.length,1);
});
test('latest template choice wins when replies arrive out of order',async()=>{
  const h=harness(),old=h.change();h.nodes.get('template').value='C';const fresh=h.change();h.pending[1].resolve({template_id:'C'});await fresh;h.pending[0].resolve({template_id:'B'});await old;
  assert.equal(h.S.templates.template_id,'C');assert.equal(h.loads.length,1);
});
test('edits made while reading another template are retained',async()=>{
  const h=harness(),task=h.change();h.S.layout.value=2;h.S.dirty=true;h.pending[0].resolve({template_id:'B'});await task;
  assert.equal(h.S.templates.template_id,'default');assert.equal(h.S.layout.value,2);assert.equal(h.S.dirty,true);assert.equal(h.loads.length,0);
});
