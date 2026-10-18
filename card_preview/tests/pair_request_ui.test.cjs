const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
function harness(){
  const S={request:0,listRequest:0,word:{id:1},templates:{old:true},layout:{old:true},words:[{id:1}],total:1,dirty:false};
  let direction='en/zh-TW',loads=0;const nodes=new Map(),pending=[],errors=[];
  const c=vm.createContext({S,$:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},pair:()=>direction,
    busy(){},clearInspector(){},renderList(){},setLoading:stage=>S.loading=stage,
    api:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),error:e=>errors.push(e.message),
    fillTemplates(){},fillVersions(){},chooseLayout:()=>S.layout={new:true},loadWords:async()=>{loads++;S.loading=null;}});
  vm.runInContext('let pairRequest=0;'+source.slice(source.indexOf('async function loadPair(){'),source.indexOf('function fillTemplates(){')),c);
  return {S,c,pending,nodes,errors,setPair:p=>direction=p,loads:()=>loads};
}
test('language load clears old templates, layout and words; failure ends loading with pair retry',async()=>{
  const h=harness(),task=h.c.loadPair();assert.equal(h.S.templates,null);assert.equal(h.S.layout,null);assert.equal(h.S.words.length,0);assert.equal(h.S.loading,'pair');
  h.pending[0].reject(new Error('offline'));await task;assert.equal(h.S.loading,null);assert.match(h.nodes.get('card').innerHTML,/data-retry-pair/);assert.equal(h.loads(),0);
});
test('old failed language load does not add an error after newer success',async()=>{
  const h=harness(),old=h.c.loadPair();h.setPair('en/fr');const fresh=h.c.loadPair();h.pending[1].resolve({id:'fr'});await fresh;h.pending[0].reject(new Error('old outage'));await old;
  assert.equal(h.S.templates.id,'fr');assert.equal(h.loads(),1);assert.equal(h.errors.length,0);
});
test('old successful language load cannot replace current templates',async()=>{
  const h=harness(),old=h.c.loadPair();h.setPair('en/fr');const fresh=h.c.loadPair();h.pending[1].resolve({id:'fr'});await fresh;h.pending[0].resolve({id:'zh'});await old;
  assert.equal(h.S.templates.id,'fr');assert.equal(h.loads(),1);
});
test('retry queries current language and restores its template before words',async()=>{
  const h=harness(),first=h.c.loadPair();h.pending[0].reject(new Error('offline'));await first;const retry=h.c.loadPair();h.pending[1].resolve({id:'zh'});await retry;
  assert.equal(h.S.templates.id,'zh');assert.equal(h.loads(),1);assert.equal(h.nodes.get('banner').hidden,true);
});
