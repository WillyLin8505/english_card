const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
function harness({complete=false,width=0,side='front',feedback=null}={}){
  const S={side,feedback,imageFailed:false};let renders=0;
  const img={complete,naturalWidth:width,hasAttribute:()=>true,parentNode:{append(){}}};
  const buttons=['data-option','data-token','data-zone','data-reveal'].map(kind=>({disabled:false,hasAttribute:k=>k===kind}));
  const card={querySelector:q=>q==='[data-quiz-image]'?img:null,querySelectorAll:()=>buttons,contains:x=>x===img};
  const c=vm.createContext({S,$:()=>card,render:()=>renders++,document:{createElement:()=>({dataset:{},setAttribute(){}})}});
  vm.runInContext(source.slice(source.indexOf('function quizImageReady('),source.indexOf("$('card').addEventListener('load'")),c);
  return {S,img,buttons,c,renders:()=>renders};
}
test('pending photo disables choices, tokens, zones and answer reveal; loaded image enables them',()=>{
  const h=harness();h.c.syncQuizImage();assert.ok(h.buttons.every(b=>b.disabled));assert.equal(h.c.quizImageReady(),false);
  h.img.complete=true;h.img.naturalWidth=100;h.c.quizImageEvent({target:h.img});assert.ok(h.buttons.every(b=>!b.disabled));assert.equal(h.c.quizImageReady(),true);
});
test('broken required image renders failure, detached events and back images are ignored',()=>{
  const h=harness({complete:true});h.c.quizImageEvent({target:h.img});assert.equal(h.S.imageFailed,true);assert.equal(h.renders(),1);
  h.c.quizImageEvent({target:{hasAttribute:()=>true}});assert.equal(h.renders(),1);
  const back=harness({complete:true,side:'back'});back.c.quizImageEvent({target:back.img});assert.equal(back.S.imageFailed,false);
});
test('loaded photo never re-enables already graded options',()=>{
  const h=harness({complete:true,width:100,feedback:{correct:true}});h.c.syncQuizImage();assert.equal(h.buttons[0].disabled,true);assert.equal(h.buttons[1].disabled,false);
});
test('front image alternative text does not reveal native answer; back keeps it',()=>{
  const c=vm.createContext({S:{word:{native_language:'zh-TW'}},esc:String,link:()=>''});
  vm.runInContext(source.split('\n').find(l=>l.startsWith('function imageHtml(')),c);
  const i={url:'/image',alt_native:{'zh-TW':'蘋果'}};
  assert.match(c.imageHtml(i,true),/alt="題目圖片"/);assert.doesNotMatch(c.imageHtml(i,true),/蘋果/);assert.match(c.imageHtml(i),/alt="蘋果"/);
});
