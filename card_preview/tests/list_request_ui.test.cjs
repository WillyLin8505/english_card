const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
const list = source.slice(source.indexOf('async function loadWords('),source.indexOf('function renderList(){'));
function harness() {
  const S={request:0,listRequest:0,total:100,offset:0,limit:40,word:{id:209},words:[]};
  const nodes=new Map([['scope',{value:'full'}],['search',{value:'cup'}]]);
  const pending=[], selections=[], errors=[], loads=[];
  let direction='target=en&native=zh-TW', random;
  const context=vm.createContext({S,Math:{floor:Math.floor,random:()=>.5},
    pair:()=>direction,$:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},
    api:()=>new Promise((resolve,reject)=>pending.push({resolve,reject})),
    renderList(){},clearInspector(){},busy(){S.exercise=null;},setLoading:s=>{S.loading=s;},
    selectWord:async id=>selections.push(id),error:e=>errors.push(e.message),toast(){},
    on:(id,event,fn)=>{if(id==='random')random=fn;},
    loadWords:async id=>loads.push(id)});
  const start=source.indexOf('async function randomWord(){');
  if(start>=0)vm.runInContext(source.slice(start,source.indexOf('function on(',start)),context);
  vm.runInContext(source.split('\n').find(line=>line.startsWith("on('random',")),context);
  return {S,nodes,pending,selections,errors,loads,context,
    random:()=>random(),changePair:p=>{direction=p;},useList:()=>vm.runInContext(list,context)};
}
test('random result from an earlier search cannot change current page or selection',async()=>{
  const h=harness();const task=h.random();
  h.nodes.get('search').value='wind';h.S.listRequest++;
  h.pending[0].resolve({items:[{id:209}],total:100});await task;
  assert.equal(h.S.offset,0);assert.deepEqual(h.loads,[]);
});
test('random result from an earlier language cannot trigger loads in the new language',async()=>{
  const h=harness();const task=h.random();
  h.changePair('target=fr&native=zh-TW');h.S.listRequest++;
  h.pending[0].resolve({items:[{id:209}],total:100});await task;
  assert.equal(h.S.offset,0);assert.deepEqual(h.loads,[]);
});
test('stale list failure is ignored after a newer successful list',async()=>{
  const h=harness();h.useList();const old=h.context.loadWords();
  const next=h.context.loadWords();
  h.pending[1].resolve({items:[{id:603}],total:1});await next;
  h.pending[0].reject(new Error('old outage'));await old;
  assert.deepEqual(h.errors,[]);assert.deepEqual(h.selections,[603]);
});
test('current list failure ends loading with a retry and no old answer',async()=>{
  const h=harness();h.useList();const task=h.context.loadWords();
  h.pending[0].reject(new Error('offline'));await task;
  assert.equal(h.S.word,null);assert.equal(h.S.loading,null);
  assert.match(h.nodes.get('card').innerHTML,/data-retry-list/);
});
test('current random sample selects its row and containing page',async()=>{
  const h=harness();const task=h.random();
  h.pending[0].resolve({items:[{id:209}],total:100});await task;
  assert.equal(h.S.offset,40);assert.deepEqual(h.loads,[209]);
});
test('current random failure is retryable; stale failure has no error',async()=>{
  const h=harness();const task=h.random();
  h.pending[0].reject(new Error('offline'));await task;
  assert.equal(h.S.loading,null);assert.match(h.nodes.get('card').innerHTML,/data-retry-random/);
  const stale=h.random();h.nodes.get('search').value='wind';h.S.listRequest++;
  h.pending[1].reject(new Error('old outage'));await stale;
  assert.deepEqual(h.errors,['offline']);
});
test('successful empty list clears the prior error and old answer',async()=>{
  const h=harness();h.useList();h.nodes.set('banner',{hidden:false});
  const task=h.context.loadWords();h.pending[0].resolve({items:[],total:0});
  assert.equal(await task,true);assert.equal(h.S.word,null);assert.equal(h.S.loading,null);
  assert.equal(h.nodes.get('banner').hidden,true);assert.match(h.nodes.get('card').innerHTML,/沒有符合/);
});
