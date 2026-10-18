const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
function harness(){
  let p='target=en&native=zh-TW';const pending=[],toasts=[],errors=[];
  const S={templates:{template_id:'default',draft:{count:1}},layout:{count:1},dirty:true,saving:null};
  const nodes=new Map([['version',{value:'draft'}]]);let choices=0;
  const c=vm.createContext({S,structuredClone,JSON,$:id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id);},pair:()=>p,
    templateQuery:()=>p+'&template_id='+S.templates.template_id,
    api:(path,body)=>new Promise((resolve,reject)=>pending.push({path,body,resolve,reject})),
    fillVersions:v=>nodes.get('version').value=v,chooseLayout:()=>{choices++;S.layout=structuredClone(S.templates.draft);},render(){},toast:t=>toasts.push(t),error:e=>errors.push(e.message)});
  vm.runInContext(source.slice(source.indexOf('async function save(publish){'),source.indexOf("on('save-layout'",source.indexOf('async function save(publish){'))),c);
  return {S,c,pending,toasts,errors,nodes,choices:()=>choices,pair:value=>p=value};
}
test('edits made after save began are retained and remain dirty',async()=>{
  const h=harness(),task=h.c.save(false);h.S.layout.count=2;h.S.dirty=true;
  h.pending[0].resolve({draft:{count:1},versions:[]});await task;
  assert.equal(h.S.layout.count,2);assert.equal(h.S.dirty,true);assert.equal(h.choices(),0);
});
test('old language save cannot overwrite current templates or toast',async()=>{
  const h=harness(),task=h.c.save(false);h.pair('target=en&native=fr');const current={template_id:'fr',draft:{count:5}};h.S.templates=current;h.S.layout={count:5};h.S.dirty=false;h.S.saving=null;
  h.pending[0].resolve({draft:{count:1},versions:[]});await task;
  assert.equal(h.S.templates,current);assert.equal(h.S.layout.count,5);assert.equal(h.toasts.length,0);
});
test('old save failure cannot show error in a new language',async()=>{
  const h=harness(),task=h.c.save(false);h.pair('target=en&native=fr');h.S.templates={template_id:'fr'};h.S.saving=null;
  h.pending[0].reject(new Error('old outage'));await task;assert.equal(h.errors.length,0);
});
test('repeated publish while in flight creates only one request',async()=>{
  const h=harness(),task=h.c.save(true),duplicate=h.c.save(true);assert.equal(h.pending.length,1);await duplicate;
  h.pending[0].resolve({draft:{count:1},versions:[{version:1}]});await task;
  assert.equal(h.nodes.get('version').value,'local:1');assert.equal(h.S.dirty,false);
});
test('current failure retains draft and enables retry',async()=>{
  const h=harness(),task=h.c.save(false);h.pending[0].reject(new Error('offline'));await task;
  assert.equal(h.S.dirty,true);assert.equal(h.S.saving,null);assert.equal(h.errors.length,1);assert.equal(h.nodes.get('save-layout').disabled,false);
});
test('save completion keeps a later selected version without claiming unsaved edits',async()=>{
  const h=harness(),task=h.c.save(false);h.nodes.get('version').value='local:7';h.S.layout={count:7};h.S.dirty=false;
  h.pending[0].resolve({draft:{count:1},versions:[{version:7}]});await task;
  assert.equal(h.nodes.get('version').value,'local:7');assert.equal(h.S.layout.count,7);assert.equal(h.choices(),0);assert.doesNotMatch(h.toasts[0],/尚未儲存/);
});
