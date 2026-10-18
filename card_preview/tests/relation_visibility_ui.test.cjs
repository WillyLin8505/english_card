const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
test('learning back hides rare relations even in expanded content while retaining common C2 words',()=>{
  const S={sense:1,word:{relations:[
    {source_sense_id:1,relation:'homophones',target_word:'froot',translation:'水果',hide_by_default:true},
    {source_sense_id:1,relation:'homophones',target_word:'hidden',translation:'罕見',detail:{hide_by_default:true}},
    {source_sense_id:1,relation:'homophones',target_word:'common',translation:'常用',cefr:'C2'}]},
    layout:{show_translation:true,relation_limits:{homophones:5}},catalog:{relations:{homophones:'同音字'}}};
  const c=vm.createContext({S,selectedSense:()=>null,good:v=>typeof v==='string'&&v.trim(),esc:String});
  vm.runInContext(source.slice(source.indexOf('function sectionContent('),source.indexOf('function imageHtml(')),c);
  for(const all of [false,true]){
    const html=c.sectionContent('relations',5,all);
    assert.doesNotMatch(html,/froot|hidden/);assert.match(html,/common/);
  }
});
