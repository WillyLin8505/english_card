const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const load = source.slice(source.indexOf('async function loadExercise(){'), source.indexOf('function clearInspector(){'));
const select = source.slice(source.indexOf('async function selectWord(id){'), source.indexOf('async function loadExercise(){'));
function harness() {
  const nodes = new Map();
  const pending = [];
  const S = {request:0, word:{id:209, images:[]}, kind:'cloze', sense:636};
  const renders = [], errors = [];
  const context = vm.createContext({S, selectedSense:()=>null, pair:()=>'',
    $:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},
    busy:()=>{S.exercise=null;S.side='front';},
    setLoading:stage=>{S.loading=stage;},
    render:()=>renders.push(S.exercise), error:e=>errors.push(e.message),
    clearInspector(){}, renderInspector(){}, renderList(){},
    document:{querySelectorAll:()=>[]}, good:v=>typeof v==='string'&&!!v.trim(),
    api:()=>new Promise((resolve,reject)=>pending.push({resolve,reject}))});
  vm.runInContext(select+'\n'+load, context);
  return {S, pending, renders, errors, nodes, context};
}
test('exercise failure ends loading and renders a retryable failure', async () => {
  const h = harness();
  const task = h.context.loadExercise();
  h.pending[0].reject(new Error('offline'));
  await task;
  assert.equal(h.S.loading, null);
  assert.equal(h.S.exercise.available, false);
  assert.equal(h.S.exercise.request_failed, true);
  assert.equal(h.renders.length, 1);
});
test('failed word request clears the old word and offers retry for the intended id', async () => {
  const h = harness();
  const task = h.context.selectWord(17013);
  assert.equal(h.S.word, null);
  assert.equal(h.S.sense, 0);
  assert.equal(h.S.loading, 'word');
  h.pending[0].reject(new Error('offline'));
  await task;
  assert.equal(h.S.loading, null);
  assert.match(h.nodes.get('card').innerHTML, /data-retry-word="17013"/);
  assert.equal(h.S.word, null);
});
test('stale word failure cannot overwrite the latest word or exercise', async () => {
  const h = harness();
  const old = h.context.selectWord(209);
  const next = h.context.selectWord(17013);
  const fresh = {id:17013,images:[],senses:[{id:77,translation:'打嗝'}]};
  h.pending[1].resolve(fresh);
  await new Promise(resolve=>setImmediate(resolve));
  h.pending[2].resolve({kind:'cloze',available:true});
  await next;
  h.pending[0].reject(new Error('old outage'));
  await old;
  assert.equal(h.S.word,fresh);
  assert.equal(h.S.sense,77);
  assert.deepEqual(h.errors,[]);
  assert.equal(h.S.loading,null);
});
test('a stale failing request cannot overwrite a newer successful exercise', async () => {
  const h = harness();
  const old = h.context.loadExercise();
  h.S.kind='photo_choice';
  const next = h.context.loadExercise();
  const fresh = {kind:'photo_choice',available:true};
  h.pending[1].resolve(fresh);
  await next;
  h.pending[0].reject(new Error('old outage'));
  await old;
  assert.equal(h.S.exercise, fresh);
  assert.equal(h.S.loading, null);
  assert.deepEqual(h.errors, []);
  assert.equal(h.renders.length, 1);
});
