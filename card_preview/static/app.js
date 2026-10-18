'use strict';
const initial = new URLSearchParams(location.search);
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const good = v => typeof v === 'string' && v.trim() && !v.includes('\ufffd');
const names = {en:'英文',fr:'法文','zh-TW':'繁體中文'};
const posNames = {noun:'名詞',verb:'動詞',adj:'形容詞',adjective:'形容詞',adv:'副詞',adverb:'副詞',phrase:'片語',det:'限定詞',intj:'感嘆詞',num:'數詞',pron:'代名詞',prep:'介系詞',conj:'連接詞',unknown:'詞性待補'};
const posList=list=>list.map(p=>posNames[p]||p).join('・');
const S = {catalog:null, templates:null, layout:null, word:null, words:[], total:0, offset:0, limit:40,
  kind:'cloze', preferredKind:'cloze', side:'front', sense:0, exercise:null, request:0, listRequest:0, selected:null, audio:null,
  imageIndex:0, feedback:null, placements:new Set(), dragSelected:null, match:null, dirty:false, toastTimer:null, loading:null, imageFailed:false, saving:null};
function resetMatch(){S.match={selected:null,done:new Set(),mistakes:0,wrong:null,token:0};}
resetMatch();
function pair(){return `target=${encodeURIComponent($('target').value)}&native=${encodeURIComponent($('native').value)}`;}
async function api(path, body){
  const r = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json','X-Preview-Token':S.catalog.token},body:JSON.stringify(body)} : {});
  const data = await r.json(); if(!r.ok) throw new Error(data.error || '操作失敗'); return data;
}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(S.toastTimer);S.toastTimer=setTimeout(()=>$('toast').hidden=true,4000);}
function error(err){$('banner').hidden=false;$('banner').textContent=err.message;}
function stopAudio(){if(S.audio){S.audio.pause();S.audio=null;}}
function busy(){S.imageFailed=false;stopAudio();S.side='front';S.exercise=null;S.feedback=null;S.placements.clear();S.dragSelected=null;resetMatch();S.imageIndex=0;}
function setLoading(stage){S.loading=stage;const changing=stage==='pair'||stage==='word'||stage==='list';$('front').disabled=!!stage;$('back').disabled=!!stage;$('sense').disabled=changing;$('template').disabled=changing;$('version').disabled=changing;$('search').disabled=!S.templates;$('scope').disabled=!S.templates;$('new-template').disabled=!S.templates;for(const id of ['show-ratings','show-translation','save-layout','publish-layout','reset-layout'])$(id).disabled=!S.layout||$('version').value!=='draft'||(!!S.saving&&['save-layout','publish-layout'].includes(id));for(const id of ['previous','next','random'])$(id).disabled=changing;$('list-prev').disabled=changing||S.offset===0;$('list-next').disabled=changing||S.offset+S.limit>=S.total;document.querySelectorAll('.kind').forEach(b=>{b.disabled=changing||!S.word||(['photo_choice','photo_recall','drag'].includes(b.dataset.kind)&&!S.word.images.length);});}
function selectedSense(){return S.word?.senses.find(s=>s.id===S.sense);}
function currentVersion(){return ($('template')?.selectedOptions[0]?.textContent||'')+' · '+$('version').selectedOptions[0]?.textContent || '本機草稿';}
function source(text){return S.layout?.show_sources && text ? `<div class="source">${esc(text)}</div>`:'';}
function link(url,label){try{const u=new URL(url);if(!['https:','http:'].includes(u.protocol))return esc(label);return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;}catch{return esc(label);}}
async function init(){
  try{
    S.catalog=await api('/api/catalog');
    $('target').innerHTML=S.catalog.languages.map(x=>`<option value="${esc(x.code)}">${esc(names[x.code]||x.code)}</option>`).join('');
    $('target').value=initial.get('target')||'en'; fillNatives();if(initial.has('native'))$('native').value=initial.get('native');if(initial.has('q'))$('search').value=initial.get('q');
    $('kinds').innerHTML=S.catalog.kinds.map(k=>`<button class="kind ${k.id===S.kind?'active':''}" data-kind="${k.id}"><span class="kind-icon">${esc(k.icon)}</span><strong>${esc(k.name)}</strong><small>${esc(k.description)}</small></button>`).join('');
    await loadPair();
  }catch(e){error(e);$('card').innerHTML='<div class="empty">無法連接詞庫。確認資料庫啟動後，點「更新資料」重試。</div>';}
}
function fillNatives(){const before=$('native').value;const pairs=S.catalog.pairs.filter(p=>p.target_language===$('target').value);$('native').innerHTML=pairs.map(p=>`<option value="${esc(p.native_language)}">${esc(names[p.native_language]||p.native_language)}</option>`).join('');$('native').value=pairs.some(p=>p.native_language===before)?before:pairs.some(p=>p.native_language==='zh-TW')?'zh-TW':pairs[0]?.native_language;}
let pairRequest=0;
async function loadPair(){
  const seq=++pairRequest,p=pair();S.templateRequest=(S.templateRequest||0)+1;S.request++;S.listRequest++;busy();S.word=null;S.sense=0;S.offset=0;S.dirty=false;S.templates=null;S.layout=null;S.saving=null;S.words=[];S.total=0;
  clearInspector();renderList();for(const id of ['template','version','sections','relation-limits'])$(id).innerHTML='';setLoading('pair');
  $('card').innerHTML='<div class="empty">載入這個語言方向的資料…</div>';
  let t;
  try{t=await api('/api/templates?'+p);}catch(e){if(seq!==pairRequest||p!==pair())return false;setLoading(null);$('card').innerHTML='<div class="empty">這個語言方向的模板讀取失敗，請在連線恢復後重試。</div><button class="primary reveal" data-retry-pair>重試語言資料</button>';error(e);return false;}
  if(seq!==pairRequest||p!==pair())return false;
  $('banner').hidden=true;S.templates=t;fillTemplates();fillVersions();chooseLayout();return loadWords();
}
function fillTemplates(){if($('template')){$('template').innerHTML=S.templates.choices.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');$('template').value=S.templates.template_id;}}
function templateQuery(){return pair()+'&template_id='+encodeURIComponent(S.templates?.template_id||'default');}
function fillVersions(selected='draft'){
  $('version').innerHTML='<option value="draft">正式共用草稿</option>'+S.templates.versions.map(v=>`<option value="local:${v.version}">正式版本 v${v.version}</option>`).join('')+S.templates.upstream.map(t=>`<option value="updraft:${t.id}">${esc(t.name)} · 後台草稿</option>`+t.versions.map(v=>`<option value="up:${t.id}:${v.version}">${esc(t.name)} · 後台 v${v.version}${v.version===t.published_version?'（目前發布）':''}</option>`).join('')).join('');
  $('version').value=selected;
}
function chooseLayout(){
  const key=$('version').value;let layout;
  if(key==='draft')layout=S.templates.draft;
  else if(key.startsWith('local:'))layout=S.templates.versions.find(v=>v.version===Number(key.split(':')[1])).layout;
  else{const bits=key.split(':');const t=S.templates.upstream.find(t=>t.id===Number(bits[1]));layout=bits[0]==='updraft'?t.draft:t.versions.find(v=>v.version===Number(bits[2])).layout;}
  if(!layout || layout.schema_version!==1 || !Array.isArray(layout.sections)){
    S.layout=null;$('card').innerHTML='<div class="empty">這份後台模板尚未提供預覽格式 v1。請選擇正式共用草稿，或依 README 對接模板欄位。</div>';$('sections').innerHTML='';return;
  }
  S.layout=structuredClone(layout);S.dirty=false;renderEditor();render();
}
async function loadWords(preferId){
  const seq=++S.listRequest;const p=pair();
  ++S.request;busy();S.word=null;S.sense=0;clearInspector();setLoading('list');$('card').innerHTML='<div class="empty">讀取詞條列表…</div>';$('word-list').innerHTML='<div class="empty">讀取詞條列表…</div>';
  let data;
  try{data=await api(`/api/words?${p}&scope=${$('scope').value}&q=${encodeURIComponent($('search').value)}&offset=${S.offset}&limit=${S.limit}`);}catch(e){if(seq!==S.listRequest||p!==pair())return false;S.words=[];S.total=0;setLoading(null);renderList();$('card').innerHTML='<div class="empty">詞條列表讀取失敗，請在連線恢復後重試。</div><button class="primary reveal" data-retry-list>重試詞條列表</button>';$('word-list').innerHTML='<div class="empty">詞條列表讀取失敗</div>';error(e);return false;}
  if(seq!==S.listRequest||p!==pair())return;
  $('banner').hidden=true;S.words=data.items;S.total=data.total;renderList();
  if(S.words.length)await selectWord(S.words.some(w=>w.id===preferId)?preferId:S.words[0].id);
  else{++S.request;S.word=null;S.exercise=null;setLoading(null);$('card').innerHTML='<div class="empty">沒有符合的詞條。可以換個搜尋字詞或語言方向。</div>';clearInspector();}
  return true;
}
function renderList(){
  $('word-count').textContent=S.total;$('list-page').textContent=S.total?`${S.offset+1}–${Math.min(S.offset+S.limit,S.total)} / ${S.total}`:'0 / 0';
  $('list-prev').disabled=S.offset===0;$('list-next').disabled=S.offset+S.limit>=S.total;
  $('word-list').innerHTML=S.words.map(w=>`<button class="word ${S.word?.id===w.id?'active':''}" data-word="${w.id}"><strong>${esc(w.lemma)}</strong>${w.entry_type==='phrase'?'<span class="badge">片語</span>':''}<span class="pos">${esc(posList(w.pos_list||[w.pos]))}</span><small>${good(w.meaning)?esc(w.meaning):'母語釋義待補'}</small><div class="sub">${esc(w.cefr||'程度待補')} · ${w.example_count} 組例句 ${w.status==='stub'?'· 關係詞待匯入':''}</div></button>`).join('') || '<div class="empty">沒有結果</div>';
}
async function selectWord(id){
  const seq=++S.request;busy();S.word=null;S.sense=0;clearInspector();setLoading('word');renderList();$('card').innerHTML='<div class="empty">讀取實際詞條…</div>';
  let word;
  try{word=await api('/api/card/'+id+'?'+pair());}catch(e){if(seq!==S.request)return;setLoading(null);$('card').innerHTML=`<div class="empty">詞條讀取失敗，請在連線恢復後重試。</div><button class="primary reveal" data-retry-word="${id}">重試這個詞條</button>`;error(e);return;}
  if(seq!==S.request)return;
  S.word=word;
  document.querySelectorAll('.kind').forEach(b=>{const requiresImage=['photo_choice','photo_recall','drag'].includes(b.dataset.kind);b.disabled=requiresImage&&!word.images.length;b.title=b.disabled?'這個詞條尚無可用圖片':'';const desc=b.querySelector('small');if(desc)desc.textContent=b.disabled?'尚無圖片':S.catalog.kinds.find(k=>k.id===b.dataset.kind).description;});
  const preferred=S.preferredKind||S.kind;
  S.kind=!word.images.length&&['photo_choice','photo_recall','drag'].includes(preferred)?'cloze':preferred;
  S.sense=word.senses.find(s=>good(s.translation))?.id || word.senses[0]?.id || 0;
  renderList();renderInspector();await loadExercise();
}
async function loadExercise(){
  const seq=++S.request;busy();if(!S.word){setLoading(null);return;}
  setLoading('exercise');
  $('card').innerHTML='<div class="empty">載入字卡…</div>';
  let x;
  try{x=await api(`/api/exercise/${selectedSense()?.lexeme_id??S.word.id}?${pair()}&kind=${S.kind}&sense=${S.sense}`);}catch(e){if(seq!==S.request)return;setLoading(null);S.exercise={kind:S.kind,sense_id:S.sense,available:false,request_failed:true,reasons:['題目讀取失敗，請在連線恢復後重試。']};render();error(e);return;}
  if(seq!==S.request)return;
  setLoading(null);$('banner').hidden=true;S.exercise=x;render();
}
function clearInspector(){$('sense').innerHTML='';}
function renderInspector(){
  const w=S.word;if(!w)return;
  const option=s=>`<option value="${s.id}">#${s.id} ${esc(good(s.translation)?s.translation:s.definition||'未填義項')}</option>`;
  $('sense').innerHTML=(w.usages?.length>1?w.usages.map(u=>`<optgroup label="${esc(posNames[u.pos]||u.pos)}">${w.senses.filter(s=>s.lexeme_id===u.lexeme_id).map(option).join('')}</optgroup>`).join(''):w.senses.map(option).join(''))||'<option value="0">沒有義項</option>';$('sense').value=S.sense;
}
const zoneOf=s=>s.visible?s.side:'unused';
// Indexes into S.layout.sections of the blocks shown in one zone, in display order.
function zoneRows(zone){return S.layout.sections.map((s,i)=>i).filter(i=>zoneOf(S.layout.sections[i])===zone);}
function renderEditor(){
  if(!S.layout)return;
  const editable=$('version').value==='draft';
  const block=(s,index,first,last)=>`<div class="editor-row" draggable="${editable}" data-index="${index}"><div class="line"><span class="drag-grip" aria-hidden="true">⠿</span><input type="checkbox" data-setting="visible" data-index="${index}" ${s.visible?'checked':''} ${!editable||s.key==='answer'?'disabled':''} aria-label="顯示${esc(S.catalog.sections[s.key])}"><strong>${esc(S.catalog.sections[s.key]||s.key)}</strong><button data-move="-1" data-index="${index}" ${!editable||first?'disabled':''} aria-label="上移${esc(S.catalog.sections[s.key])}">↑</button><button data-move="1" data-index="${index}" ${!editable||last?'disabled':''} aria-label="下移${esc(S.catalog.sections[s.key])}">↓</button></div><details class="block-settings"><summary>區塊設定</summary><div class="controls"><select data-setting="side" data-index="${index}" ${!editable?'disabled':''} aria-label="${esc(S.catalog.sections[s.key])}位置"><option value="unused" ${!s.visible?'selected':''}>未使用</option><option value="back" ${s.visible&&s.side==='back'?'selected':''}>背面</option>${['hint','meaning'].includes(s.key)?`<option value="front" ${s.visible&&s.side==='front'?'selected':''}>正面</option>`:''}</select><span>上限</span><input type="number" min="1" max="${S.catalog.limits[s.key]}" value="${s.limit}" data-setting="limit" data-index="${index}" ${!editable?'disabled':''} aria-label="${esc(S.catalog.sections[s.key])}數量"><label><input type="checkbox" data-setting="collapsed" data-index="${index}" ${s.collapsed?'checked':''} ${!editable?'disabled':''}>收合</label><label><input type="checkbox" data-setting="expand_all" data-index="${index}" ${s.expand_all?'checked':''} ${!editable?'disabled':''}>展開全部</label></div></details></div>`;
  $('sections').innerHTML=[['front','正面 · 提示'],['back','背面 · 答案與內容'],['unused','未使用的區塊']].map(([zone,title])=>`<section class="compose-zone" data-drop="${zone}"><h3>${title}</h3><p class="drop-hint">${zone==='front'?'放入字首或母語提示':zone==='back'?'拖曳區塊到這裡':'拖到正面或背面即可加入'}</p>${zoneRows(zone).map((i,k,rows)=>block(S.layout.sections[i],i,k===0,k===rows.length-1)).join('')}</section>`).join('');
  $('relation-limits').innerHTML='<p class="aside-note">每類關係詞獨立上限</p>'+Object.entries(S.catalog.relations).map(([key,label])=>`<label class="relation-control">${esc(label)}<input type="number" min="0" max="20" value="${S.layout.relation_limits?.[key]??3}" data-relation="${key}" ${!editable?'disabled':''}></label>`).join('');
  $('show-ratings').checked=S.layout.show_ratings;$('show-translation').checked=S.layout.show_translation;
  for(const id of ['show-ratings','show-translation','save-layout','publish-layout','reset-layout'])$(id).disabled=!editable||(!!S.saving&&['save-layout','publish-layout'].includes(id));
  let copyButton=$('copy-version');if(!copyButton){copyButton=document.createElement('button');copyButton.id='copy-version';copyButton.textContent='複製此版本為草稿';copyButton.addEventListener('click',()=>{const saved=structuredClone(S.layout);$('version').value='draft';S.layout=saved;renderEditor();markDirty();toast('已載入為草稿；發布後會建立新版本。');});$('publish-layout').parentNode.append(copyButton);}copyButton.hidden=editable;
}
function markDirty(){S.dirty=true;render();}
function sectionContent(key,limit,all=false){
  const w=S.word,s=selectedSense(),n=all?Infinity:limit;
  const translated=S.layout.show_translation;
  if(key==='hint'){
    // Never reveal a whole short word: at least one letter remains hidden.
    const hint=w.lemma.split(/(\s+)/).map(token=>{const letters=[...token];if(/^\s+$/.test(token))return token;let shown=0;const count=letters.filter(c=>/\p{L}/u.test(c)).length;const allowed=Math.min(limit,Math.max(0,count-1));return letters.map(c=>!(/\p{L}/u.test(c))?c:shown++<allowed?c:'_').join('');}).join('');
    return `<div class="hint">${esc(hint)}</div>`;
  }
  if(key==='meaning')return s&&good(s.translation)?`<div class="meaning"><span class="pos-label">${esc(posNames[s.usage_pos||w.pos]||s.usage_pos||w.pos)}</span>${esc(s.translation)}</div>`:'';
  if(key==='answer')return `<div class="answer-title">${esc(w.lemma)}</div><div class="answer-meta">${esc(posList(w.usages?w.usages.map(u=>u.pos):[w.pos]))}${w.entry_type==='phrase'?' · <span class="badge">片語</span>':''} ${w.cefr?' · '+esc(w.cefr):''} ${w.zipf!=null?' · 頻率 '+esc(w.zipf):''}</div>`;
  if(key==='pronunciation'){
    const ipa=w.pronunciations.filter(p=>p.kind==='ipa').slice(0,n);const audio=w.audio.slice(0,n);
    return ipa.map(p=>`<div class="audio-row"><span>${esc(p.value)}</span><small class="micro">${esc(p.accent||'')} · ${esc(p.source)}</small></div>`).join('')+audio.map(a=>`<div class="audio-row"><span class="micro">${esc(a.accent||'單字真人發音')}</span><button data-audio="${a.id}">▶ 播放</button></div>${source([a.source,a.license,a.attribution].filter(Boolean).join(' · '))}`).join('');
  }
  // Senses are grouped by POS usage; the limit applies to each usage.
  if(key==='senses')return (w.usages||[{lexeme_id:undefined}]).map(u=>{const list=w.senses.filter(x=>u.lexeme_id===undefined||x.lexeme_id===u.lexeme_id).slice(0,n);return list.length?(w.usages?.length>1?`<p class="usage-label">${esc(posNames[u.pos]||u.pos)}</p>`:'')+list.map(x=>`<p><span class="micro">#${x.id}</span> ${esc(x.definition||'')}</p>${translated&&good(x.translation)?`<p class="translation">${esc(x.translation)}${x.is_ai?' · AI 翻譯':''}${x.is_override?' · 使用者覆寫':''}</p>`:''}${source([x.definition_source,x.translation_source].filter(Boolean).join(' / '))}`).join(''):'';}).join('');
  if(key==='images'){
    const images=w.images.filter(i=>i.sense_id===S.sense);if(!images.length)return '';
    const chosen=Array.from({length:Math.min(images.length,Number.isFinite(n)?n:images.length)},(_,j)=>images[(S.imageIndex+j)%images.length]);return chosen.map(i=>imageHtml(i)).join('')+(images.length>chosen.length?'<button data-image-next>換一張同義項圖片 ↻</button>':'');
  }
  if(key==='examples'){const examples=w.examples.filter(e=>e.sense_id===S.sense);return examples.length?'<ol>'+examples.slice(0,n).map(e=>`<li>${esc(e.text)}${translated&&good(e.translation)?`<p class="translation">${esc(e.translation)}${e.is_ai?' · AI 翻譯':''}</p>`:''}${source([e.source,e.license].filter(Boolean).join(' · '))}</li>`).join('')+'</ol>':'';}
  if(key==='forms')return w.forms.slice(0,n).map(f=>`<span class="chip">${esc(f.form)} <small>${esc(f.field)}</small></span>`).join('');
  if(key==='relations'){
    const verified=w.relations.filter(r=>r.source_sense_id===S.sense&&!r.hide_by_default&&r.detail?.hide_by_default!==true);
    const groups=Object.groupBy?Object.groupBy(verified,r=>r.relation):verified.reduce((a,r)=>((a[r.relation]??=[]).push(r),a),{});
    return Object.entries(groups).map(([type,rs])=>{const count=all?Infinity:(S.layout.relation_limits?.[type]??limit);return count?`<p class="micro">${esc(S.catalog.relations[type]||type)}</p>`+rs.slice(0,count).map(r=>`<p>${esc(r.target_word)} <span class="micro">${esc(r.pos)}</span>${translated&&good(r.translation)?`<br><span class="translation">${esc(r.translation)}${r.is_ai?' · AI 翻譯':''}</span>`:''}</p>`).join(''):'';}).join('');
  }
  if(key==='etymology')return w.etymology.map(e=>`${e.text?'<p>'+esc(e.text)+'</p>':''}${translated&&good(e.translation)?'<p class="translation">'+esc(e.translation)+'</p>':''}`+['root','prefix','suffix'].map(k=>(e[k]||[]).map(v=>`<span class="chip">${esc(typeof v==='string'?v:JSON.stringify(v))}</span>`).join('')).join('')).join('');
  if(key==='sources'){const seen=new Set();return w.provenance.filter(p=>{let k=p.source+'|'+p.license;if(seen.has(k))return false;seen.add(k);return true;}).slice(0,n).map(p=>`<p class="micro">${esc(p.source)} · ${esc(p.license||'授權待補')}<br>${esc(p.attribution||'')}</p>`).join('');}
  return '';
}
function imageHtml(i,quiz=false){return `<figure class="image-figure"><img src="${esc(i.url)}" ${quiz?'data-quiz-image':''} alt="${esc(quiz?'題目圖片':i.alt_native?.[S.word.native_language]||'已核准詞義圖片')}"><figcaption>${esc(i.author||i.attribution||'')} · ${esc(i.license_code)} · ${link(i.page_url,i.source)}</figcaption></figure>`;}
function sectionsHtml(){
  return S.layout.sections.filter(s=>s.visible&&s.side===S.side).map(s=>{
    const html=sectionContent(s.key,s.limit);if(!html)return '';
    if(['hint','meaning','answer'].includes(s.key))return html;
    const all=s.expand_all?sectionContent(s.key,s.limit,true):html;
    let content=html;if(all!==html)content=`<div class="limited">${html}</div><details class="show-all"><summary>展開全部</summary>${all}</details>`;
    const title=esc(S.catalog.sections[s.key]);return s.collapsed?`<details class="content-block"><summary>${title}</summary>${content}</details>`:`<section class="content-block"><h3>${title}</h3>${content}</section>`;
  }).join('');
}
function blockedReasonsHtml(exercise){const reasons=[...new Set((Array.isArray(exercise?.reasons)?exercise.reasons:[]).filter(good))];return reasons.length?`<ul class="blocked-list">${reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:'<p>這一題尚缺必要資料，請切換詞義或詞條。</p>';}
function render(){
  if(S.loading){$('card').innerHTML=`<div class="empty">${S.loading==='word'?'讀取實際詞條…':S.loading==='list'?'讀取詞條列表…':S.loading==='pair'?'載入這個語言方向的資料…':'載入字卡…'}</div>`;return;}
  if(!S.word||!S.layout)return;
  $('preview-kind').textContent=S.catalog.kinds.find(k=>k.id===S.kind).name;
  $('template-label').textContent=currentVersion()+(S.dirty?' · 尚未儲存':'');
  $('front').classList.toggle('active',S.side==='front');$('back').classList.toggle('active',S.side==='back');
  document.querySelectorAll('.kind').forEach(b=>b.classList.toggle('active',b.dataset.kind===S.kind));
  const x=S.exercise;
  // Incomplete cards can still be inspected on the back, but cannot be presented as a valid exercise.
  if(S.side==='front'&&(!x||!x.available)){
    $('card').innerHTML=x?`<div class="card-top"><span>PREVIEW</span><span>題目暫不可用</span></div><div class="empty"><div class="empty-symbol">◌</div><h3 class="blocked-title">${x.request_failed?'連線暫時中斷':'這一題還沒準備好'}</h3>${blockedReasonsHtml(x)}</div>${x.request_failed?'<button class="primary reveal" data-retry-exercise>重試這一題</button>':''}<button class="reveal" data-reveal>查看已有的背面資料</button>`:'<div class="empty">正在讀取題目…</div>';return;
  }
  if(S.side==='front'&&S.imageFailed){$('card').innerHTML='<div class="empty"><h3>圖片載入失敗</h3><p>暫時無法顯示題目圖片，請在連線恢復後重試。</p></div><button class="primary reveal" data-retry-exercise>重試這一題</button><button class="reveal" data-reveal>查看已有的背面資料</button>';return;}
  let content='';
  if(S.side==='back')content=sectionsHtml();
  else if(x.mode==='typed')content=`<p class="micro">${esc(x.instruction)}</p><div class="exercise-prompt">${esc(x.prompt)}</div><p class="translation">${esc(x.example.translation)}</p><form id="cloze-form"><label>你的答案<input id="cloze-answer" autocomplete="off" spellcheck="false" required ${S.feedback?'disabled':''}></label><button class="primary" ${S.feedback?'disabled':''}>核對原句</button></form>${S.feedback?`<p class="result-note">${S.feedback.correct?'與原句相符！':'原句使用：'+esc(x.answer)+'。其他填法可能也通順，這裡練習目前詞條。'}</p><p>${esc(x.example.text)}</p>`:''}`;
  else if(x.mode==='match')content=matchHtml(x);
  // The layout's front blocks (hint / meaning) now only appear under the photo.
  else if(S.kind==='photo_recall')content=`<div class="content-block">${imageHtml(x.images[S.imageIndex%x.images.length],true)}${x.images.length>1?'<button data-image-next>換一張圖片 ↻</button>':''}</div>${sectionsHtml()}`;
  else if(S.kind==='drag')content=dragHtml(x);
  else if(S.kind==='photo_choice')content=`<p class="choice-instruction">${esc(x.instruction||'觀察圖片，選出最適合的標籤。')}</p>${x.image?imageHtml(x.image,true):''}<div class="exercise-prompt photo-prompt">${esc(x.prompt||'哪個單字最適合當作這張圖片的標籤？')}</div><div class="options photo-options">${x.options.map((o,i)=>`<button class="option ${S.feedback&&o.id===x.correct_id?'correct':S.feedback?.selected===o.id?'wrong':''}" data-option="${o.id}" ${S.feedback?'disabled':''}><span class="option-key">${String.fromCharCode(65+i)}</span><strong>${esc(o.label)}</strong>${S.feedback?`<small>${esc(o.translation)}</small>`:''}</button>`).join('')}</div>${S.feedback?`<div class="result-note choice-result"><strong>${S.feedback.correct?'答對了！':'答案是 '+esc(x.options.find(o=>o.id===x.correct_id)?.label||'')}</strong><span>${S.feedback.correct?'這個標籤符合圖片中的主要物件。':'看看圖片的主要物件，再比較三個單字的意思。'}</span></div>`:''}`;
  else if(S.kind==='similar')content=`<p class="choice-instruction">${esc(x.instruction)}</p><div class="exercise-prompt photo-prompt">${esc(x.prompt)}</div><p class="translation">${esc(x.example.translation)}</p><div class="options photo-options">${x.options.map((o,i)=>`<button class="option ${S.feedback&&o.id===x.correct_id?'correct':S.feedback?.selected===o.id?'wrong':''}" data-option="${o.id}" ${S.feedback?'disabled':''}><span class="option-key">${String.fromCharCode(65+i)}</span><strong>${esc(o.label)}</strong>${S.feedback?`<small>${esc(o.translation)}</small>`:''}</button>`).join('')}</div>${S.feedback?`<div class="result-note choice-result"><strong>${S.feedback.correct?'答對了！':'答案是 '+esc(x.options.find(o=>o.id===x.correct_id)?.label||'')}</strong><span>${esc(x.example.text)}</span></div>${x.options.map(o=>`<p class="micro"><strong>${esc(o.label)}</strong> · ${esc(o.translation)}<br>${esc(o.reason)}</p>`).join('')}`:''}`;
  else content=`${x.image?imageHtml(x.image,true):''}<div class="exercise-prompt">${esc(x.prompt||'哪個單字最符合這張圖片？')}</div><div class="options">${x.options.map(o=>`<button class="option ${S.feedback&&o.id===x.correct_id?'correct':S.feedback?.selected===o.id?'wrong':''}" data-option="${o.id}" ${S.feedback?'disabled':''}>${esc(o.label)}</button>`).join('')}</div>${S.feedback?`<p class="result-note">${S.feedback.correct?'答對了。':'再比較一下正確答案。'}</p>${x.example?`<p>${esc(x.example.text)}</p><p>${esc(x.example.translation)}</p>`:''}${x.options.map(o=>`<p class="micro"><strong>${esc(o.label)}</strong> · ${esc(o.translation)}<br>${esc(o.reason)}</p>`).join('')}`:''}`;
  const canReveal=S.kind==='photo_recall'||S.feedback||S.placements.size===x?.options?.length||(x?.mode==='match'&&S.match.done.size===x.pairs.length);
  const frontAction=['photo_choice','similar','drag','cloze'].includes(S.kind)?'作答':'回想';
  const ratings=[['Again','忘記'],['Hard','吃力'],['Good','記得'],['Easy','很容易']];
  $('card').innerHTML=`<div class="card-top"><span>${S.side==='front'?'TAKE A MOMENT':'A LITTLE MORE ABOUT THIS WORD'}</span><span>${S.side==='front'?frontAction:'答案'}</span></div><div class="card-main">${content}</div>${S.side==='front'&&canReveal?'<button class="primary reveal" data-reveal>顯示答案 →</button>':''}${S.side==='back'?'<button class="reveal" data-front>回到正面</button>':''}${S.side==='back'&&S.layout.show_ratings?'<div class="ratings">'+ratings.map(([key,label])=>`<button data-rating="${key}"><strong>${key}</strong><small>${label} · 僅模擬</small></button>`).join('')+'</div>':''}`;
  syncQuizImage();
}
function quizImageReady(){const img=$('card').querySelector('[data-quiz-image]');return !img||(img.complete&&img.naturalWidth>0);}
function syncQuizImage(){
  const card=$('card'),img=card.querySelector('[data-quiz-image]');if(!img||S.side!=='front')return;
  if(img.complete&&img.naturalWidth===0){S.imageFailed=true;render();return;}
  const ready=quizImageReady();card.querySelectorAll('[data-option],[data-token],[data-zone],[data-reveal]').forEach(b=>{b.disabled=!ready||(b.hasAttribute('data-option')&&!!S.feedback);});
  let status=card.querySelector('[data-image-status]');if(!ready&&!status){status=document.createElement('p');status.dataset.imageStatus='';status.className='micro';status.setAttribute('role','status');img.parentNode.append(status);}if(status){status.textContent=ready?'':'圖片載入中…';status.hidden=ready;}
}
function quizImageEvent(e){if(!e.target.hasAttribute?.('data-quiz-image')||!$('card').contains(e.target)||S.side!=='front')return;syncQuizImage();}
$('card').addEventListener('load',quizImageEvent,true);
$('card').addEventListener('error',quizImageEvent,true);
// Rows share one height and have no gap, so row i is centred at i*100+50 in the SVG's viewBox.
function matchHtml(x){
  const m=S.match,byId=Object.fromEntries(x.pairs.map(p=>[p.id,p])),rows=x.pairs.length;
  const item=(side,id,row)=>{const p=byId[id],done=m.done.has(id),selected=m.selected?.side===side&&m.selected.id===id,wrong=m.wrong?.[side]===id;
    return `<button class="match-item ${side}${done?' matched':''}${selected?' selected':''}${wrong?' wrong':''}" style="grid-row:${row+1}" data-match-side="${side}" data-match-id="${id}" aria-pressed="${selected}" ${done?'disabled':''}>${side==='native'?esc(p.translation):esc(p.label)}</button>`;};
  const lines=[...m.done].map(id=>`<line x1="0" y1="${x.native_order.indexOf(id)*100+50}" x2="100" y2="${x.target_order.indexOf(id)*100+50}" vector-effect="non-scaling-stroke"/>`).join('');
  const finished=m.done.size===rows;
  return `<p class="choice-instruction">${esc(x.instruction)}</p><div class="exercise-prompt photo-prompt">${esc(x.prompt)}</div>
<div class="match-head"><span>${esc(names[S.word.native_language]||S.word.native_language)}</span><span>${esc(names[S.word.language]||S.word.language)}</span></div>
<div class="match-board">${x.native_order.map((id,i)=>item('native',id,i)).join('')}<svg class="match-lines" style="grid-row:1 / span ${rows}" viewBox="0 0 100 ${rows*100}" preserveAspectRatio="none" aria-hidden="true">${lines}</svg>${x.target_order.map((id,i)=>item('target',id,i)).join('')}</div>
${finished?`<div class="result-note choice-result"><strong>${m.mistakes?`完成！過程中連錯 ${m.mistakes} 次`:'全部連對！'}</strong>${x.pairs.map(p=>`<span><b>${esc(p.label)}</b> ${esc(posNames[p.pos]||p.pos||'')} · ${esc(p.translation)} · ${esc(p.relation)}</span>`).join('')}</div>`:''}`;
}
function pickMatch(side,id){
  const m=S.match;if(m.done.has(id))return;
  if(!m.selected||m.selected.side===side){m.selected=m.selected?.side===side&&m.selected.id===id?null:{side,id};render();return;}
  const pick={[m.selected.side]:m.selected.id,[side]:id};m.selected=null;
  if(pick.native===pick.target){m.done.add(id);render();return;}
  m.mistakes++;m.wrong=pick;const token=++m.token;render();
  setTimeout(()=>{if(S.match===m&&m.token===token){m.wrong=null;render();}},650);
}
function dragHtml(x){return `<p class="micro">拖曳詞籤，或先點詞籤再點圖片區域。</p><div class="drag-area"><img data-quiz-image src="${esc(x.image.url)}" alt="練習圖片">${x.options.map((o,i)=>`<button class="drop-zone ${S.placements.has(o.id)?'correct':''}" data-zone="${o.id}" aria-label="圖片區域 ${i+1}" style="z-index:${1+x.options.filter(p=>p.box[2]*p.box[3]>o.box[2]*o.box[3]).length};left:${o.box[0]*100}%;top:${o.box[1]*100}%;width:${o.box[2]*100}%;height:${o.box[3]*100}%">${S.placements.has(o.id)?esc(o.label):''}</button>`).join('')}${x.options.map((o,i)=>`<span class="zone-marker" aria-hidden="true" style="left:${o.box[0]*100}%;top:${o.box[1]*100}%;transform:translateY(${24*x.options.slice(0,i).filter(p=>Math.abs(p.box[0]-o.box[0])<1e-3&&Math.abs(p.box[1]-o.box[1])<1e-3).length}px)">${i+1}${S.placements.has(o.id)?' '+esc(o.label):''}</span>`).join('')}</div><div class="word-tokens">${x.options.filter(o=>!S.placements.has(o.id)).map(o=>`<button draggable="true" data-token="${o.id}" class="word-token ${S.dragSelected===o.id?'selected':''}">${esc(o.label)}</button>`).join('')}</div>${S.placements.size===x.options.length?'<p class="result-note">位置全部正確！可以查看完整資料。</p>':''}`;}
function play(id){stopAudio();const a=S.word.audio.find(a=>a.id===id);if(!a)return;S.audio=new Audio(a.url);S.audio.play().catch(()=>toast('音檔無法播放，請確認檔案狀態或標記音檔問題。'));}
function reveal(){if(S.loading||!S.word)return;stopAudio();S.side='back';render();if($('autoplay').checked&&S.word.audio.length)play(S.word.audio[0].id);}
function showFront(){if(S.loading)return;stopAudio();S.side='front';S.feedback=null;S.placements.clear();S.dragSelected=null;resetMatch();render();}
function place(id,point=null){if(!quizImageReady()||S.imageFailed||S.dragSelected==null)return;const option=S.exercise.options.find(o=>o.id===id);if(!option)return;const selected=S.exercise.options.find(o=>o.id===S.dragSelected);const sameBox=selected&&selected.box.every((v,i)=>Math.abs(v-option.box[i])<1e-6);const inside=point&&selected&&point[0]>=selected.box[0]&&point[0]<=selected.box[0]+selected.box[2]&&point[1]>=selected.box[1]&&point[1]<=selected.box[1]+selected.box[3];if(point?inside:S.dragSelected===id||sameBox){S.placements.add(S.dragSelected);toast('位置正確');}else toast('位置不符，詞籤已回到原位。');S.dragSelected=null;render();}
function dragPoint(e){
  if(e.type!=='drop'&&!(e.detail>0))return null;
  const image=$('card').querySelector('.drag-area img');if(!image)return null;
  const r=image.getBoundingClientRect();if(!r.width||!r.height)return null;
  return [(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height];
}
async function navigate(delta){const idx=S.words.findIndex(w=>w.id===S.word?.id);let next=idx+delta;if(next>=0&&next<S.words.length)return selectWord(S.words[next].id);if(delta>0&&S.offset+S.limit<S.total){S.offset+=S.limit;return loadWords();}if(delta<0&&S.offset>0){S.offset=Math.max(0,S.offset-S.limit);if(await loadWords()===false||!S.words.length)return;return selectWord(S.words[S.words.length-1].id);}toast('已到目前搜尋範圍的邊界');}
async function randomWord(){
  if(!S.total)return;
  const seq=++S.listRequest,request=++S.request,p=pair(),scope=$('scope').value,q=$('search').value,index=Math.floor(Math.random()*S.total);
  busy();S.word=null;S.sense=0;clearInspector();setLoading('list');$('card').innerHTML='<div class="empty">隨機抽樣中…</div>';
  let data;
  try{data=await api(`/api/words?${p}&scope=${scope}&q=${encodeURIComponent(q)}&offset=${index}&limit=1`);}catch(e){if(seq!==S.listRequest||request!==S.request||p!==pair()||scope!==$('scope').value||q!==$('search').value)return;setLoading(null);$('card').innerHTML='<div class="empty">隨機抽樣讀取失敗，請在連線恢復後重試。</div><button class="primary reveal" data-retry-random>重試隨機抽樣</button>';error(e);return;}
  if(seq!==S.listRequest||request!==S.request||p!==pair()||scope!==$('scope').value||q!==$('search').value)return;
  S.offset=data.items.length?Math.floor(index/S.limit)*S.limit:0;
  return loadWords(data.items[0]?.id);
}

function on(id,event,fn){$(id)?.addEventListener(event,e=>Promise.resolve().then(()=>fn(e)).catch(error));}
on('refresh','click',async()=>{ $('banner').hidden=true;if(!S.catalog)return init();if(!S.templates)return loadPair();if(await loadWords(S.word?.id)===true)toast('已更新實際資料'); });
on('target','change',()=>{fillNatives();return loadPair();});on('native','change',loadPair);
on('scope','change',()=>{S.offset=0;return loadWords();});
let searchTimer;on('search','input',()=>{clearTimeout(searchTimer);S.listRequest++;S.request++;searchTimer=setTimeout(()=>{S.offset=0;loadWords().catch(error);},250);});
on('word-list','click',e=>{const b=e.target.closest('[data-word]');if(b)return selectWord(Number(b.dataset.word));});
on('list-prev','click',()=>{S.offset=Math.max(0,S.offset-S.limit);return loadWords();});on('list-next','click',()=>{S.offset+=S.limit;return loadWords();});
on('kinds','click',e=>{const b=e.target.closest('[data-kind]');if(b){S.kind=b.dataset.kind;S.preferredKind=S.kind;return loadExercise();}});
on('sense','change',()=>{S.sense=Number($('sense').value);return loadExercise();});
on('device','change',()=>{$('stage').className='stage '+$('device').value;});
on('front','click',showFront);on('back','click',()=>{if(S.word)reveal();});
on('previous','click',()=>navigate(-1));on('next','click',()=>navigate(1));
on('random','click',randomWord);
on('version','change',()=>{busy();chooseLayout();return loadExercise();});
$('card').addEventListener('submit',e=>{if(e.target.id!=='cloze-form')return;e.preventDefault();const actual=$('cloze-answer').value.trim().normalize('NFKC').toLocaleLowerCase();S.feedback={correct:actual===S.exercise.answer.normalize('NFKC').toLocaleLowerCase()};render();});
on('card','click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.hasAttribute('data-retry-pair'))return loadPair();
  if(b.hasAttribute('data-retry-list'))return loadWords();
  if(b.hasAttribute('data-retry-random'))return randomWord();
  if(b.hasAttribute('data-retry-exercise'))return loadExercise();
  if(b.hasAttribute('data-retry-word'))return selectWord(Number(b.dataset.retryWord));
  if((b.dataset.option||b.dataset.token||b.dataset.zone||b.hasAttribute('data-reveal'))&&!quizImageReady())return;
  if(b.hasAttribute('data-reveal'))reveal();
  if(b.hasAttribute('data-front'))showFront();
  if(b.dataset.audio)play(Number(b.dataset.audio));
  if(b.dataset.rating)toast(`已模擬「${b.dataset.rating}」；未寫入任何學習紀錄。`);
  if(b.hasAttribute('data-image-next')){S.imageIndex++;render();}
  if(b.dataset.option){S.feedback={selected:Number(b.dataset.option),correct:Number(b.dataset.option)===S.exercise.correct_id};render();}
  if(b.dataset.token){S.dragSelected=Number(b.dataset.token);render();}
  if(b.dataset.matchSide)pickMatch(b.dataset.matchSide,Number(b.dataset.matchId));
  if(b.dataset.zone)place(Number(b.dataset.zone),dragPoint(e));
});
$('card').addEventListener('dragstart',e=>{const b=e.target.closest('[data-token]');if(b&&quizImageReady()&&!S.imageFailed){S.dragSelected=Number(b.dataset.token);e.dataTransfer.setData('text/plain',b.dataset.token);}});
$('card').addEventListener('dragover',e=>{if(e.target.closest('[data-zone]'))e.preventDefault();});
$('card').addEventListener('drop',e=>{const b=e.target.closest('[data-zone]');if(b){e.preventDefault();place(Number(b.dataset.zone),dragPoint(e));}});
function moveBlock(index,zone,before=null){
  if($('version').value!=='draft')return;
  const row=S.layout.sections[index];if(!row||before===index)return;
  if(zone==='front'&&!['hint','meaning'].includes(row.key)){toast('正面可放字首或母語提示；答案內容請放背面。');return;}
  if(row.key==='answer'&&zone!=='back'){toast('背面需要保留答案單字。');return;}
  if(row.visible&&row.side==='front'&&zone!=='front'&&!S.layout.sections.some((s,i)=>i!==index&&s.visible&&s.side==='front')){toast('正面至少保留一個提示區塊。');return;}
  const beforeKey=before===null?null:S.layout.sections[before]?.key;
  row.visible=zone!=='unused';if(row.visible)row.side=zone;
  S.layout.sections.splice(index,1);
  const at=beforeKey?S.layout.sections.findIndex(s=>s.key===beforeKey):-1;
  S.layout.sections.splice(at<0?S.layout.sections.length:at,0,row);
  renderEditor();markDirty();
}
on('sections','change',e=>{
  if($('version').value!=='draft')return;const key=e.target.dataset.setting;if(!key)return;
  const index=Number(e.target.dataset.index),row=S.layout.sections[index];
  if(key==='side'||key==='visible'){moveBlock(index,key==='side'?e.target.value:e.target.checked?row.side:'unused');renderEditor();return;}
  const value=e.target.type==='checkbox'?e.target.checked:Number(e.target.value);
  if(key==='limit'&&(!Number.isInteger(value)||value<1||value>S.catalog.limits[row.key])){renderEditor();toast('數量超出允許範圍');return;}
  row[key]=value;markDirty();
});
// Arrows swap with the neighbouring block of the same zone, not with hidden blocks in between.
on('sections','click',e=>{const b=e.target.closest('[data-move]');if(!b||$('version').value!=='draft')return;const from=Number(b.dataset.index),rows=zoneRows(zoneOf(S.layout.sections[from])),to=rows[rows.indexOf(from)+Number(b.dataset.move)];if(to===undefined)return;const list=S.layout.sections;[list[from],list[to]]=[list[to],list[from]];renderEditor();markDirty();});
// A block lands before the first row whose midpoint is below the pointer, or at the end of the zone.
function dropSpot(y,hit){
  const zone=hit?.closest?.('[data-drop]');if(!zone)return null;
  const rows=[...zone.querySelectorAll('.editor-row')];
  const next=rows.find(r=>{const b=r.getBoundingClientRect();return y<b.top+b.height/2;});
  return {zone:zone.dataset.drop,before:next?Number(next.dataset.index):null,el:zone,next,last:rows.at(-1)};
}
function clearSpot(){document.querySelectorAll('.drop-active,.drop-before,.drop-after').forEach(x=>x.classList.remove('drop-active','drop-before','drop-after'));}
function showSpot(spot){clearSpot();if(!spot)return;spot.el.classList.add('drop-active');if(spot.next)spot.next.classList.add('drop-before');else spot.last?.classList.add('drop-after');}
let draggedSection=null;
$('sections').addEventListener('dragstart',e=>{const row=e.target.closest('.editor-row');if(!row||$('version').value!=='draft')return;draggedSection=Number(row.dataset.index);e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',String(draggedSection));row.classList.add('dragging');});
$('sections').addEventListener('dragover',e=>{const spot=dropSpot(e.clientY,e.target);if(spot&&draggedSection!==null){e.preventDefault();e.dataTransfer.dropEffect='move';showSpot(spot);}});
$('sections').addEventListener('drop',e=>{e.preventDefault();const spot=dropSpot(e.clientY,e.target);clearSpot();if(spot&&draggedSection!==null)moveBlock(draggedSection,spot.zone,spot.before);draggedSection=null;});
$('sections').addEventListener('dragend',()=>{draggedSection=null;clearSpot();document.querySelectorAll('.dragging').forEach(x=>x.classList.remove('dragging'));});
// Pointer dragging also supports touch and browser hosts without native HTML drag events.
let pointerBlock=null;
$('sections').addEventListener('pointerdown',e=>{
  const row=e.target.closest('.editor-row');
  if(!row||e.button!==0||$('version').value!=='draft'||e.target.closest('input,select,button,summary,.block-settings'))return;
  pointerBlock={index:Number(row.dataset.index),row,x:e.clientX,y:e.clientY,moved:false};
  row.setPointerCapture(e.pointerId);e.preventDefault();
});
document.addEventListener('pointermove',e=>{
  if(!pointerBlock)return;
  if(Math.hypot(e.clientX-pointerBlock.x,e.clientY-pointerBlock.y)<5)return;
  pointerBlock.moved=true;pointerBlock.row.classList.add('dragging');
  showSpot(dropSpot(e.clientY,document.elementFromPoint(e.clientX,e.clientY)));
});
document.addEventListener('pointerup',e=>{
  if(!pointerBlock)return;const drag=pointerBlock;pointerBlock=null;
  const spot=dropSpot(e.clientY,document.elementFromPoint(e.clientX,e.clientY));
  clearSpot();drag.row.classList.remove('dragging');
  if(drag.moved&&spot)moveBlock(drag.index,spot.zone,spot.before);
});
document.addEventListener('pointercancel',()=>{pointerBlock?.row.classList.remove('dragging');pointerBlock=null;clearSpot();});
on('relation-limits','change',e=>{const key=e.target.dataset.relation;if(!key)return;const n=Number(e.target.value);if(!Number.isInteger(n)||n<0||n>20){toast('關係詞上限需為 0～20');renderEditor();return;}S.layout.relation_limits[key]=n;markDirty();});
on('show-ratings','change',()=>{S.layout.show_ratings=$('show-ratings').checked;markDirty();});on('show-translation','change',()=>{S.layout.show_translation=$('show-translation').checked;markDirty();});
on('reset-layout','click',()=>{const limits={hint:1,meaning:1,answer:1,pronunciation:1,senses:3,images:1,examples:5,forms:5,relations:3,etymology:1,sources:10};S.layout={schema_version:1,sections:Object.keys(S.catalog.sections).map(key=>({key,side:['hint','meaning'].includes(key)?'front':'back',visible:true,limit:limits[key],collapsed:['etymology','sources'].includes(key),expand_all:true})),relation_limits:Object.fromEntries(Object.keys(S.catalog.relations).map(k=>[k,3])),show_ratings:true,show_translation:true,show_sources:true};renderEditor();markDirty();});
async function save(publish){
  if(S.saving||!S.layout||!S.templates)return false;
  const token={},owner=S.templates,p=pair(),query=templateQuery(),layout=structuredClone(S.layout),version=$('version').value;
  S.saving=token;for(const id of ['save-layout','publish-layout'])$(id).disabled=true;
  try{
    const result=await api(`/api/templates/${publish?'publish':'save'}?${query}`,{layout});
    if(S.saving!==token||p!==pair()||S.templates!==owner)return false;
    const changed=JSON.stringify(S.layout)!==JSON.stringify(layout)||$('version').value!==version;
    S.templates={...S.templates,...result};
    if(changed){const selected=$('version').value;fillVersions(selected);render();toast(S.dirty&&selected==='draft'?(publish?'已發布送出時的版本；目前編輯內容尚未儲存。':'送出時的草稿已儲存；目前編輯內容尚未儲存。'):(publish?'已發布送出時的版本。':'送出時的草稿已儲存。'));}
    else{S.dirty=false;fillVersions(publish?'local:'+result.versions[0].version:'draft');chooseLayout();toast(publish?'已發布共用版型；App 將於詞庫同步後套用。':'正式共用草稿已儲存。');}
    return true;
  }catch(e){if(S.saving===token&&p===pair()&&S.templates===owner)error(e);return false;}
  finally{if(S.saving===token){S.saving=null;for(const id of ['save-layout','publish-layout'])$(id).disabled=!S.layout||$('version').value!=='draft';}}
}
on('save-layout','click',()=>save(false));on('publish-layout','click',()=>save(true));
window.addEventListener('beforeunload',e=>{if(S.dirty){e.preventDefault();e.returnValue='';}});
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||$('template-dialog')?.open)return;if(e.code==='Space'&&S.word){e.preventDefault();if(S.side==='front')reveal();else showFront();}});
async function changeTemplate(){
  if(!S.templates)return false;
  const selected=$('template').value,previous=S.templates.template_id,p=pair(),seq=S.templateRequest=(S.templateRequest||0)+1;
  const active=()=>seq===S.templateRequest&&p===pair()&&S.templates?.template_id===previous;
  try{
    if(S.dirty){const saved=await save(false);if(!active())return false;if(!saved||S.dirty){fillTemplates();render();return false;}}
    const layout=JSON.stringify(S.layout),version=$('version').value;
    const result=await api('/api/templates?'+p+'&template_id='+encodeURIComponent(selected));
    if(!active())return false;
    if(JSON.stringify(S.layout)!==layout||$('version').value!==version){fillTemplates();render();toast('內容已變更，請再次切換模板。');return false;}
    S.templates=result;fillTemplates();fillVersions();busy();chooseLayout();await loadExercise();return true;
  }catch(e){if(active()){fillTemplates();render();error(e);}return false;}
}
on('template','change',changeTemplate);
on('new-template','click',()=>{$('template-name').value='';$('template-clone').checked=false;$('template-dialog').showModal();$('template-name').focus();});
on('template-cancel','click',()=>$('template-dialog').close());
on('template-form','submit',async e=>{e.preventDefault();const result=await api('/api/templates/create?'+pair(),{name:$('template-name').value,layout:$('template-clone').checked?S.layout:null});S.templates={...result,upstream:S.templates.upstream};fillTemplates();fillVersions();chooseLayout();$('template-dialog').close();toast('新模板已建立，可開始拖曳編排。');});
init();
