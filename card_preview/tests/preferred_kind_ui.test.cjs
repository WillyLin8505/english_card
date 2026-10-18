const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');

function selectWordFunction(){
  const start=source.indexOf('async function selectWord(');
  const end=source.indexOf('async function loadExercise(',start);
  return source.slice(start,end);
}

test('an image template is restored after visiting a word without images',async()=>{
  const words=[
    {id:1,images:[],senses:[{id:11,translation:'沒有圖'}]},
    {id:2,images:[{url:'/photo.jpg'}],senses:[{id:22,translation:'有圖'}]},
  ];
  const S={request:0,kind:'cloze',preferredKind:'photo_choice',word:null,sense:0,
    catalog:{kinds:[
      {id:'cloze',description:'填空'},
      {id:'photo_choice',description:'照片選字'},
      {id:'photo_recall',description:'照片回想'},
      {id:'drag',description:'拖曳'},
    ]}};
  const buttons=S.catalog.kinds.map(k=>({dataset:{kind:k.id},querySelector:()=>({textContent:''})}));
  const context=vm.createContext({S,busy(){},clearInspector(){},setLoading(){},renderList(){},
    renderInspector(){},loadExercise:async()=>{},pair:()=>'',good:v=>!!v,error(){},
    api:async path=>words.find(w=>path.includes('/'+w.id+'?')),
    document:{querySelectorAll:()=>buttons},$:()=>({innerHTML:''})});
  vm.runInContext(selectWordFunction(),context);

  await context.selectWord(1);
  assert.equal(S.kind,'cloze');
  assert.equal(S.preferredKind,'photo_choice');

  await context.selectWord(2);
  assert.equal(S.kind,'photo_choice');
  assert.equal(S.preferredKind,'photo_choice');
});
