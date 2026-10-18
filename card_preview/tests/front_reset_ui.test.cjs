const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
function harness(){
  const S={word:{id:1},side:'back',loading:null,feedback:{correct:true},placements:new Set([1,11]),dragSelected:7694,match:{done:new Set([1]),selected:{id:1}}};
  const handlers={};let stops=0,renders=0;
  const context=vm.createContext({S,$:()=>({open:false}),stopAudio:()=>stops++,render:()=>renders++,
    resetMatch:()=>{S.match={done:new Set(),selected:null};},
    on:(id,event,fn)=>{handlers[id]=fn;},document:{addEventListener:(event,fn)=>{handlers[event]=fn;}}});
  const helper=source.split('\n').find(line=>line.startsWith('function showFront('));
  if(helper)vm.runInContext(helper,context);
  vm.runInContext(source.split('\n').find(line=>line.startsWith("on('front',")),context);
  const start=source.indexOf("on('card','click',e=>{");
  vm.runInContext(source.slice(start,source.indexOf("$('card').addEventListener('dragstart'",start)),context);
  vm.runInContext(source.split('\n').find(line=>line.startsWith("document.addEventListener('keydown'")),context);
  return {S,handlers,stops:()=>stops,renders:()=>renders};
}
for(const entry of ['top','inline','keyboard']){
  test(`${entry} front clears answer feedback, placed labels and selected token`,()=>{
    const h=harness();
    if(entry==='top')h.handlers.front({});
    if(entry==='inline')h.handlers.card({target:{closest:()=>({dataset:{},hasAttribute:name=>name==='data-front'})}});
    if(entry==='keyboard')h.handlers.keydown({code:'Space',target:{tagName:'DIV'},preventDefault(){}});
    assert.equal(h.S.side,'front');assert.equal(h.S.feedback,null);
    assert.equal(h.S.placements.size,0);assert.equal(h.S.dragSelected,null);
    assert.equal(h.S.match.done.size,0);assert.equal(h.S.match.selected,null);
    assert.equal(h.stops(),1);assert.equal(h.renders(),1);
  });
}
