'use strict';
const ADMIN = document.body.classList.contains('data-admin');
const initial = new URLSearchParams(location.search);
const $ = id => document.getElementById(id);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const good = v => typeof v === 'string' && v.trim() && !v.includes('\ufffd');
const names = {en:'英文',fr:'法文','zh-TW':'繁體中文'};
const posNames = {noun:'名詞',verb:'動詞',adj:'形容詞',adjective:'形容詞',adv:'副詞',adverb:'副詞',phrase:'片語',det:'限定詞',intj:'感嘆詞',num:'數詞',pron:'代名詞',prep:'介系詞',conj:'連接詞',unknown:'詞性待補'};
const posList=list=>list.map(p=>posNames[p]||p).join('・');
const S = {catalog:null, templates:null, layout:null, word:null, words:[], total:0, offset:0, limit:40,
  kind:'cloze', side:'front', sense:0, exercise:null, request:0, listRequest:0, selected:null, audio:null,
  imageIndex:0, feedback:null, placements:new Set(), dragSelected:null, match:null, dirty:false, toastTimer:null};
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
function busy(){stopAudio();S.side='front';S.exercise=null;S.feedback=null;S.placements.clear();S.dragSelected=null;resetMatch();S.imageIndex=0;}
function selectedSense(){return S.word?.senses.find(s=>s.id===S.sense);}
function currentVersion(){return ($('template')?.selectedOptions[0]?.textContent||'')+' · '+$('version').selectedOptions[0]?.textContent || '本機草稿';}
function source(text){return S.layout?.show_sources && text ? `<div class="source">${esc(text)}</div>`:'';}
function link(url,label){try{const u=new URL(url);if(!['https:','http:'].includes(u.protocol))return esc(label);return `<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;}catch{return esc(label);}}
function displayDate(value){if(!value)return '—';const date=new Date(value);return Number.isNaN(date.getTime())?esc(value):date.toLocaleString('zh-TW',{hour12:false});}

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
  const seq=++pairRequest;S.request++;S.listRequest++;busy();S.word=null;S.offset=0;S.dirty=false;
  $('card').innerHTML='<div class="empty">載入這個語言方向的資料…</div>';
  const t=await api('/api/templates?'+pair());if(seq!==pairRequest)return;
  S.templates=t;fillTemplates();fillVersions();chooseLayout();await loadWords();
}
function fillTemplates(){if($('template')){$('template').innerHTML=S.templates.choices.map(t=>`<option value="${esc(t.id)}">${esc(t.name)}</option>`).join('');$('template').value=S.templates.template_id;}}
function templateQuery(){return pair()+'&template_id='+encodeURIComponent(S.templates?.template_id||'default');}
function fillVersions(selected='draft'){
  $('version').innerHTML='<option value="draft">本機預覽草稿</option>'+S.templates.versions.map(v=>`<option value="local:${v.version}">本機預覽 v${v.version}</option>`).join('')+S.templates.upstream.map(t=>`<option value="updraft:${t.id}">${esc(t.name)} · 後台草稿</option>`+t.versions.map(v=>`<option value="up:${t.id}:${v.version}">${esc(t.name)} · 後台 v${v.version}${v.version===t.published_version?'（目前發布）':''}</option>`).join('')).join('');
  $('version').value=selected;
}
function chooseLayout(){
  const key=$('version').value;let layout;
  if(key==='draft')layout=S.templates.draft;
  else if(key.startsWith('local:'))layout=S.templates.versions.find(v=>v.version===Number(key.split(':')[1])).layout;
  else{const bits=key.split(':');const t=S.templates.upstream.find(t=>t.id===Number(bits[1]));layout=bits[0]==='updraft'?t.draft:t.versions.find(v=>v.version===Number(bits[2])).layout;}
  if(!layout || layout.schema_version!==1 || !Array.isArray(layout.sections)){
    S.layout=null;$('card').innerHTML='<div class="empty">這份後台模板尚未提供預覽格式 v1。請選擇本機預覽草稿，或依 README 對接模板欄位。</div>';$('sections').innerHTML='';return;
  }
  S.layout=structuredClone(layout);S.dirty=false;renderEditor();render();
}
async function loadWords(preferId){
  const seq=++S.listRequest;const p=pair();
  const data=await api(`/api/words?${p}&scope=${$('scope').value}&q=${encodeURIComponent($('search').value)}&offset=${S.offset}&limit=${S.limit}`);
  if(seq!==S.listRequest||p!==pair())return;
  S.words=data.items;S.total=data.total;renderList();
  if(S.words.length)await selectWord(S.words.some(w=>w.id===preferId)?preferId:S.words[0].id);
  else{++S.request;S.word=null;S.exercise=null;$('card').innerHTML='<div class="empty">沒有符合的詞條。可以換個搜尋字詞或語言方向。</div>';clearInspector();}
}
function renderList(){
  $('word-count').textContent=S.total;$('list-page').textContent=S.total?`${S.offset+1}–${Math.min(S.offset+S.limit,S.total)} / ${S.total}`:'0 / 0';
  $('list-prev').disabled=S.offset===0;$('list-next').disabled=S.offset+S.limit>=S.total;
  $('word-list').innerHTML=S.words.map(w=>`<button class="word ${S.word?.id===w.id?'active':''}" data-word="${w.id}"><strong>${esc(w.lemma)}</strong><span class="pos">${esc(posList(w.pos_list||[w.pos]))}</span><small>${good(w.meaning)?esc(w.meaning):'母語釋義待補'}</small><div class="sub">${esc(w.cefr||'程度待補')} · ${w.example_count} 組例句 ${w.status==='stub'?'· 關係詞待匯入':''}</div></button>`).join('') || '<div class="empty">沒有結果</div>';
}
async function selectWord(id){
  const seq=++S.request;busy();$('card').innerHTML='<div class="empty">讀取實際詞條…</div>';
  const word=await api('/api/card/'+id+'?'+pair());if(seq!==S.request)return;
  S.word=word;
  document.querySelectorAll('.kind').forEach(b=>{const requiresImage=['photo_choice','photo_recall','drag'].includes(b.dataset.kind);b.disabled=requiresImage&&!word.images.length;b.title=b.disabled?'這個詞條尚無可用圖片':'';const desc=b.querySelector('small');if(desc)desc.textContent=b.disabled?'尚無圖片':S.catalog.kinds.find(k=>k.id===b.dataset.kind).description;});
  if(!word.images.length&&['photo_choice','photo_recall','drag'].includes(S.kind))S.kind='cloze';
  S.sense=word.senses.find(s=>good(s.translation))?.id || word.senses[0]?.id || 0;
  renderList();renderInspector();await loadExercise();
}
async function loadExercise(){
  const seq=++S.request;busy();if(!S.word)return;
  $('card').innerHTML='<div class="empty">載入字卡…</div>';
  const x=await api(`/api/exercise/${selectedSense()?.lexeme_id??S.word.id}?${pair()}&kind=${S.kind}&sense=${S.sense}`);if(seq!==S.request)return;
  S.exercise=x;render();
}
function clearInspector(){if(!ADMIN){$('sense').innerHTML='';return;}for(const id of ['metadata','missing','provenance','issues'])$(id).innerHTML='';$('sense').innerHTML='';$('quality-badge').textContent='—';}
function renderInspector(){
  const w=S.word;if(!w)return;
  const option=s=>`<option value="${s.id}">#${s.id} ${esc(good(s.translation)?s.translation:s.definition||'未填義項')}</option>`;
  $('sense').innerHTML=(w.usages?.length>1?w.usages.map(u=>`<optgroup label="${esc(posNames[u.pos]||u.pos)}">${w.senses.filter(s=>s.lexeme_id===u.lexeme_id).map(option).join('')}</optgroup>`).join(''):w.senses.map(option).join(''))||'<option value="0">沒有義項</option>';$('sense').value=S.sense;
  const wordRoute=`http://127.0.0.1:5173/ui/#/words/${encodeURIComponent(w.language)}/${encodeURIComponent(w.native_language)}/${encodeURIComponent(w.lemma)}`;
  if(!ADMIN){$('admin-link').href='http://127.0.0.1:5173/ui/#/card-data?'+pair()+'&q='+encodeURIComponent(w.lemma);return;}
  $('edit-word').href=wordRoute;
  $('metadata').innerHTML=`<dl class="metadata"><dt>詞條 ID</dt><dd>${w.id} · ${esc(w.pos)}</dd><dt>資料來源</dt><dd>即時建置資料庫</dd><dt>詞條更新</dt><dd>${displayDate(w.updated_at)}</dd><dt>最新資料包</dt><dd>${w.release?`#${w.release.id} ${esc(w.release.file_name||'')}`:'尚未發布'}</dd><dt>預覽資料</dt><dd>目前資料庫內容，非資料包快照</dd><dt>匯出資格</dt><dd>由正式匯出流程驗證</dd></dl>`;
  $('quality-badge').textContent=w.missing.length?'資料待補齊':'文字檢查通過';$('missing-count').textContent=w.missing.length;
  $('missing').innerHTML=w.missing.map(m=>`<div class="missing-item">${esc(m.message)}</div>`).join('')||'<p class="ok-note">目前文字欄位沒有缺漏。</p>';
  const seen=new Set();const prov=w.provenance.filter(p=>{const key=JSON.stringify([p.field,p.source,p.license,p.snapshot_id]);if(seen.has(key))return false;seen.add(key);return true;});
  $('provenance').innerHTML=prov.map(p=>`<div class="provenance-item"><strong>${esc(p.field)} · ${esc(p.source)}</strong>${esc(p.license||'授權待補')}<br>${esc(p.attribution||'')}<br>快照 ${esc(p.snapshot_id??'未提供')} · ${displayDate(p.processed_at)}</div>`).join('')||'<p class="aside-note">尚無來源紀錄</p>';
  $('issue-count').textContent=w.issues.length;$('issues').innerHTML=w.issues.map(i=>`<div class="issue-item"><strong>#${i.id} ${esc(i.category)} · ${esc(i.field)}</strong>${esc(i.note)}<br>${esc(i.version)} · ${displayDate(i.created)}</div>`).join('')||'<p class="aside-note">尚未標記問題</p>';
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
  for(const id of ['show-ratings','show-translation','save-layout','publish-layout','reset-layout'])$(id).disabled=!editable;
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
  if(key==='answer')return `<div class="answer-title">${esc(w.lemma)}</div><div class="answer-meta">${esc(posList(w.usages?w.usages.map(u=>u.pos):[w.pos]))} ${w.cefr?' · '+esc(w.cefr):''} ${w.zipf!=null?' · 頻率 '+esc(w.zipf):''}</div>`;
  if(key==='pronunciation'){
    const ipa=w.pronunciations.filter(p=>p.kind==='ipa').slice(0,n);const audio=w.audio.slice(0,n);
    return ipa.map(p=>`<div class="audio-row"><span>${esc(p.value)}</span><small class="micro">${esc(p.accent||'')} · ${esc(p.source)}</small></div>`).join('')+audio.map(a=>`<div class="audio-row"><span class="micro">${esc(a.accent||'單字真人發音')}</span><button data-audio="${a.id}">▶ 播放</button></div>${source([a.source,a.license,a.attribution].filter(Boolean).join(' · '))}`).join('');
  }
  // Senses are grouped by POS usage; the limit applies to each usage.
  if(key==='senses')return (w.usages||[{lexeme_id:undefined}]).map(u=>{const list=w.senses.filter(x=>u.lexeme_id===undefined||x.lexeme_id===u.lexeme_id).slice(0,n);return list.length?(w.usages?.length>1?`<p class="usage-label">${esc(posNames[u.pos]||u.pos)}</p>`:'')+list.map(x=>`<p><span class="micro">#${x.id}</span> ${esc(x.definition||'')}</p>${translated&&good(x.translation)?`<p class="translation">${esc(x.translation)}${x.is_ai?' · AI 翻譯':''}${x.is_override?' · 使用者覆寫':''}</p>`:''}${source([x.definition_source,x.translation_source].filter(Boolean).join(' / '))}`).join(''):'';}).join('');
  if(key==='images'){
    const images=w.images.filter(i=>i.sense_id===S.sense);if(!images.length)return '';
    const chosen=Array.from({length:Math.min(images.length,Number.isFinite(n)?n:images.length)},(_,j)=>images[(S.imageIndex+j)%images.length]);return chosen.map(imageHtml).join('')+(images.length>chosen.length?'<button data-image-next>換一張同義項圖片 ↻</button>':'');
  }
  if(key==='examples'){const examples=w.examples.filter(e=>e.sense_id===S.sense);return examples.length?'<ol>'+examples.slice(0,n).map(e=>`<li>${esc(e.text)}${translated&&good(e.translation)?`<p class="translation">${esc(e.translation)}${e.is_ai?' · AI 翻譯':''}</p>`:''}${source([e.source,e.license].filter(Boolean).join(' · '))}</li>`).join('')+'</ol>':'';}
  if(key==='forms')return w.forms.slice(0,n).map(f=>`<span class="chip">${esc(f.form)} <small>${esc(f.field)}</small></span>`).join('');
  if(key==='relations'){
    const groups=Object.groupBy?Object.groupBy(w.relations,r=>r.relation):w.relations.reduce((a,r)=>((a[r.relation]??=[]).push(r),a),{});
    return Object.entries(groups).map(([type,rs])=>{const count=all?Infinity:(S.layout.relation_limits?.[type]??limit);return count?`<p class="micro">${esc(S.catalog.relations[type]||type)}</p>`+rs.slice(0,count).map(r=>`<p>${esc(r.target_word)} <span class="micro">${esc(r.pos)}</span>${translated&&good(r.translation)?`<br><span class="translation">${esc(r.translation)}${r.is_ai?' · AI 翻譯':''}</span>`:''}</p>`).join(''):'';}).join('');
  }
  if(key==='etymology')return w.etymology.map(e=>`${e.text?'<p>'+esc(e.text)+'</p>':''}${translated&&good(e.translation)?'<p class="translation">'+esc(e.translation)+'</p>':''}`+['root','prefix','suffix'].map(k=>(e[k]||[]).map(v=>`<span class="chip">${esc(typeof v==='string'?v:JSON.stringify(v))}</span>`).join('')).join('')).join('');
  if(key==='sources'){const seen=new Set();return w.provenance.filter(p=>{let k=p.source+'|'+p.license;if(seen.has(k))return false;seen.add(k);return true;}).slice(0,n).map(p=>`<p class="micro">${esc(p.source)} · ${esc(p.license||'授權待補')}<br>${esc(p.attribution||'')}</p>`).join('');}
  return '';
}
function imageHtml(i){return `<figure class="image-figure"><img src="${esc(i.url)}" alt="${esc(i.alt_native?.[S.word.native_language]||'已核准詞義圖片')}"><figcaption>${esc(i.author||i.attribution||'')} · ${esc(i.license_code)} · ${link(i.page_url,i.source)}</figcaption></figure>`;}
function sectionsHtml(){
  return S.layout.sections.filter(s=>s.visible&&s.side===S.side).map(s=>{
    const html=sectionContent(s.key,s.limit);if(!html)return '';
    if(['hint','meaning','answer'].includes(s.key))return html;
    const all=s.expand_all?sectionContent(s.key,s.limit,true):html;
    let content=html;if(all!==html)content=`<div class="limited">${html}</div><details class="show-all"><summary>展開全部</summary>${all}</details>`;
    const title=esc(S.catalog.sections[s.key]);return s.collapsed?`<details class="content-block"><summary>${title}</summary>${content}</details>`:`<section class="content-block"><h3>${title}</h3>${content}</section>`;
  }).join('');
}
function render(){
  if(!S.word||!S.layout)return;
  $('preview-kind').textContent=S.catalog.kinds.find(k=>k.id===S.kind).name;
  $('template-label').textContent=currentVersion()+(S.dirty?' · 尚未儲存':'');
  $('front').classList.toggle('active',S.side==='front');$('back').classList.toggle('active',S.side==='back');
  document.querySelectorAll('.kind').forEach(b=>b.classList.toggle('active',b.dataset.kind===S.kind));
  const x=S.exercise;
  // Incomplete cards can still be inspected on the back, but cannot be presented as a valid exercise.
  if(S.side==='front'&&(!x||!x.available)){
    $('card').innerHTML=`<div class="card-top"><span>PREVIEW</span><span>資料待補齊</span></div><div class="empty"><div class="empty-symbol">◌</div><h3 class="blocked-title">這一題還沒準備好</h3><p>先補齊必要資料，再預覽完整互動。</p>${ADMIN?`<ul class="blocked-list">${(x?.reasons||[]).map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:'<p>請到語言資料後台查看準備進度。</p>'}</div><button class="reveal" data-reveal>查看已有的背面資料</button>`;return;
  }
  let content='';
  if(S.side==='back')content=sectionsHtml();
  else if(x.mode==='typed')content=`<p class="micro">${esc(x.instruction)}</p><div class="exercise-prompt">${esc(x.prompt)}</div><p class="translation">${esc(x.example.translation)}</p><form id="cloze-form"><label>你的答案<input id="cloze-answer" autocomplete="off" spellcheck="false" required ${S.feedback?'disabled':''}></label><button class="primary" ${S.feedback?'disabled':''}>核對原句</button></form>${S.feedback?`<p class="result-note">${S.feedback.correct?'與原句相符！':'原句使用：'+esc(x.answer)+'。其他填法可能也通順，這裡練習目前詞條。'}</p><p>${esc(x.example.text)}</p>`:''}`;
  else if(x.mode==='match')content=matchHtml(x);
  // The layout's front blocks (hint / meaning) now only appear under the photo.
  else if(S.kind==='photo_recall')content=`<div class="content-block">${imageHtml(x.images[S.imageIndex%x.images.length])}${x.images.length>1?'<button data-image-next>換一張圖片 ↻</button>':''}</div>${sectionsHtml()}`;
  else if(S.kind==='drag')content=dragHtml(x);
  else if(S.kind==='photo_choice')content=`<p class="choice-instruction">${esc(x.instruction||'觀察圖片，選出最適合的標籤。')}</p>${x.image?imageHtml(x.image):''}<div class="exercise-prompt photo-prompt">${esc(x.prompt||'哪個單字最適合當作這張圖片的標籤？')}</div><div class="options photo-options">${x.options.map((o,i)=>`<button class="option ${S.feedback&&o.id===x.correct_id?'correct':S.feedback?.selected===o.id?'wrong':''}" data-option="${o.id}" ${S.feedback?'disabled':''}><span class="option-key">${String.fromCharCode(65+i)}</span><strong>${esc(o.label)}</strong>${S.feedback?`<small>${esc(o.translation)}</small>`:''}</button>`).join('')}</div>${S.feedback?`<div class="result-note choice-result"><strong>${S.feedback.correct?'答對了！':'答案是 '+esc(x.options.find(o=>o.id===x.correct_id)?.label||'')}</strong><span>${S.feedback.correct?'這個標籤符合圖片中的主要物件。':'看看圖片的主要物件，再比較三個單字的意思。'}</span></div>`:''}`;
  else if(S.kind==='similar')content=`<p class="choice-instruction">${esc(x.instruction)}</p><div class="exercise-prompt photo-prompt">${esc(x.prompt)}</div><p class="translation">${esc(x.example.translation)}</p><div class="options photo-options">${x.options.map((o,i)=>`<button class="option ${S.feedback&&o.id===x.correct_id?'correct':S.feedback?.selected===o.id?'wrong':''}" data-option="${o.id}" ${S.feedback?'disabled':''}><span class="option-key">${String.fromCharCode(65+i)}</span><strong>${esc(o.label)}</strong>${S.feedback?`<small>${esc(o.translation)}</small>`:''}</button>`).join('')}</div>${S.feedback?`<div class="result-note choice-result"><strong>${S.feedback.correct?'答對了！':'答案是 '+esc(x.options.find(o=>o.id===x.correct_id)?.label||'')}</strong><span>${esc(x.example.text)}</span></div>${x.options.map(o=>`<p class="micro"><strong>${esc(o.label)}</strong> · ${esc(o.translation)}<br>${esc(o.reason)}</p>`).join('')}`:''}`;
  else content=`${x.image?imageHtml(x.image):''}<div class="exercise-prompt">${esc(x.prompt||'哪個單字最符合這張圖片？')}</div><div class="options">${x.options.map(o=>`<button class="option ${S.feedback&&o.id===x.correct_id?'correct':S.feedback?.selected===o.id?'wrong':''}" data-option="${o.id}" ${S.feedback?'disabled':''}>${esc(o.label)}</button>`).join('')}</div>${S.feedback?`<p class="result-note">${S.feedback.correct?'答對了。':'再比較一下正確答案。'}</p>${x.example?`<p>${esc(x.example.text)}</p><p>${esc(x.example.translation)}</p>`:''}${x.options.map(o=>`<p class="micro"><strong>${esc(o.label)}</strong> · ${esc(o.translation)}<br>${esc(o.reason)}</p>`).join('')}`:''}`;
  const canReveal=S.kind==='photo_recall'||S.feedback||S.placements.size===x?.options?.length||(x?.mode==='match'&&S.match.done.size===x.pairs.length);
  const frontAction=['photo_choice','similar','drag','cloze'].includes(S.kind)?'作答':'回想';
  const ratings=[['Again','忘記'],['Hard','吃力'],['Good','記得'],['Easy','很容易']];
  $('card').innerHTML=`<div class="card-top"><span>${S.side==='front'?'TAKE A MOMENT':'A LITTLE MORE ABOUT THIS WORD'}</span><span>${S.side==='front'?frontAction:'答案'}</span></div><div class="card-main">${content}</div>${S.side==='front'&&canReveal?'<button class="primary reveal" data-reveal>顯示答案 →</button>':''}${S.side==='back'?'<button class="reveal" data-front>回到正面</button>':''}${S.side==='back'&&S.layout.show_ratings?'<div class="ratings">'+ratings.map(([key,label])=>`<button data-rating="${key}"><strong>${key}</strong><small>${label} · 僅模擬</small></button>`).join('')+'</div>':''}`;
}
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
function dragHtml(x){return `<p class="micro">拖曳詞籤，或先點詞籤再點圖片區域。</p><div class="drag-area"><img src="${esc(x.image.url)}" alt="練習圖片">${x.options.map((o,i)=>`<button class="drop-zone ${S.placements.has(o.id)?'correct':''}" data-zone="${o.id}" aria-label="圖片區域 ${i+1}" style="z-index:${1+x.options.filter(p=>p.box[2]*p.box[3]>o.box[2]*o.box[3]).length};left:${o.box[0]*100}%;top:${o.box[1]*100}%;width:${o.box[2]*100}%;height:${o.box[3]*100}%">${S.placements.has(o.id)?esc(o.label):i+1}</button>`).join('')}</div><div class="word-tokens">${x.options.filter(o=>!S.placements.has(o.id)).map(o=>`<button draggable="true" data-token="${o.id}" class="word-token ${S.dragSelected===o.id?'selected':''}">${esc(o.label)}</button>`).join('')}</div>${S.placements.size===x.options.length?'<p class="result-note">位置全部正確！可以查看完整資料。</p>':''}`;}
function play(id){stopAudio();const a=S.word.audio.find(a=>a.id===id);if(!a)return;S.audio=new Audio(a.url);S.audio.play().catch(()=>toast('音檔無法播放，請確認檔案狀態或標記音檔問題。'));}
function reveal(){stopAudio();S.side='back';render();if($('autoplay').checked&&S.word.audio.length)play(S.word.audio[0].id);}
function place(id){if(S.dragSelected==null)return;const option=S.exercise.options.find(o=>o.id===id);if(!option)return;const selected=S.exercise.options.find(o=>o.id===S.dragSelected);const sameBox=selected&&selected.box.every((v,i)=>Math.abs(v-option.box[i])<1e-6);if(S.dragSelected===id||sameBox){S.placements.add(S.dragSelected);toast('位置正確');}else toast('位置不符，詞籤已回到原位。');S.dragSelected=null;render();}
async function navigate(delta){const idx=S.words.findIndex(w=>w.id===S.word?.id);let next=idx+delta;if(next>=0&&next<S.words.length)return selectWord(S.words[next].id);if(delta>0&&S.offset+S.limit<S.total){S.offset+=S.limit;return loadWords();}if(delta<0&&S.offset>0){S.offset=Math.max(0,S.offset-S.limit);await loadWords();return selectWord(S.words[S.words.length-1].id);}toast('已到目前搜尋範圍的邊界');}

function on(id,event,fn){$(id)?.addEventListener(event,e=>Promise.resolve().then(()=>fn(e)).catch(error));}
on('refresh','click',async()=>{ $('banner').hidden=true;if(!S.catalog)return init();await loadWords(S.word?.id);toast('已更新實際資料'); });
on('target','change',()=>{fillNatives();return loadPair();});on('native','change',loadPair);
on('scope','change',()=>{S.offset=0;return loadWords();});
let searchTimer;on('search','input',()=>{clearTimeout(searchTimer);S.listRequest++;S.request++;searchTimer=setTimeout(()=>{S.offset=0;loadWords().catch(error);},250);});
on('word-list','click',e=>{const b=e.target.closest('[data-word]');if(b)return selectWord(Number(b.dataset.word));});
on('list-prev','click',()=>{S.offset=Math.max(0,S.offset-S.limit);return loadWords();});on('list-next','click',()=>{S.offset+=S.limit;return loadWords();});
on('kinds','click',e=>{const b=e.target.closest('[data-kind]');if(b){S.kind=b.dataset.kind;return loadExercise();}});
on('sense','change',()=>{S.sense=Number($('sense').value);return loadExercise();});
on('device','change',()=>{$('stage').className='stage '+$('device').value;});
on('front','click',()=>{stopAudio();S.side='front';S.feedback=null;S.placements.clear();resetMatch();render();});on('back','click',()=>{if(S.word)reveal();});
on('previous','click',()=>navigate(-1));on('next','click',()=>navigate(1));
on('random','click',async()=>{if(!S.total)return;const index=Math.floor(Math.random()*S.total);const data=await api(`/api/words?${pair()}&scope=${$('scope').value}&q=${encodeURIComponent($('search').value)}&offset=${index}&limit=1`);if(data.items.length){S.offset=Math.floor(index/S.limit)*S.limit;await loadWords(data.items[0].id);}});
on('version','change',()=>{busy();chooseLayout();return loadExercise();});
$('card').addEventListener('submit',e=>{if(e.target.id!=='cloze-form')return;e.preventDefault();const actual=$('cloze-answer').value.trim().normalize('NFKC').toLocaleLowerCase();S.feedback={correct:actual===S.exercise.answer.normalize('NFKC').toLocaleLowerCase()};render();});
on('card','click',e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.hasAttribute('data-reveal'))reveal();
  if(b.hasAttribute('data-front')){stopAudio();S.side='front';render();}
  if(b.dataset.audio)play(Number(b.dataset.audio));
  if(b.dataset.rating)toast(`已模擬「${b.dataset.rating}」；未寫入任何學習紀錄。`);
  if(b.hasAttribute('data-image-next')){S.imageIndex++;render();}
  if(b.dataset.option){S.feedback={selected:Number(b.dataset.option),correct:Number(b.dataset.option)===S.exercise.correct_id};render();}
  if(b.dataset.token){S.dragSelected=Number(b.dataset.token);render();}
  if(b.dataset.matchSide)pickMatch(b.dataset.matchSide,Number(b.dataset.matchId));
  if(b.dataset.zone)place(Number(b.dataset.zone));
});
$('card').addEventListener('dragstart',e=>{const b=e.target.closest('[data-token]');if(b){S.dragSelected=Number(b.dataset.token);e.dataTransfer.setData('text/plain',b.dataset.token);}});
$('card').addEventListener('dragover',e=>{if(e.target.closest('[data-zone]'))e.preventDefault();});
$('card').addEventListener('drop',e=>{const b=e.target.closest('[data-zone]');if(b){e.preventDefault();place(Number(b.dataset.zone));}});
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
async function save(publish){const result=await api(`/api/templates/${publish?'publish':'save'}?${templateQuery()}`,{layout:S.layout});S.templates={...S.templates,...result};S.dirty=false;fillVersions(publish?'local:'+result.versions[0].version:'draft');chooseLayout();toast(publish?'已發布本機預覽版本；正式 App 未變更。':'預覽草稿已儲存。');}
on('save-layout','click',()=>save(false));on('publish-layout','click',()=>save(true));
on('issue-open','click',()=>{if(!S.word){toast('請先選擇詞條');return;}const fields=[['layout','版面／模板'],['pos','詞性'],['sources','來源資訊'],...S.word.senses.map(s=>['sense:'+s.id,'義項 #'+s.id]),...S.word.examples.map(x=>['example:'+x.id,'例句 #'+x.id]),...S.word.relations.map(x=>['relation:'+x.id,'關係詞 '+x.target_word]),...S.word.audio.map(x=>['audio:'+x.id,'音檔 #'+x.id]),...S.word.images.map(x=>['image:'+x.sense_image_id,'圖片 #'+x.sense_image_id])];$('issue-field').innerHTML=fields.map(([v,t])=>`<option value="${esc(v)}">${esc(t)}</option>`).join('');$('issue-dialog').showModal();});
on('issue-close','click',()=>$('issue-dialog').close());
$('issue-form')?.addEventListener('submit',e=>{e.preventDefault();(async()=>{await api('/api/issues?'+pair(),{lexeme_id:S.word.id,sense_id:S.sense||null,template:S.kind,version:currentVersion()+(S.dirty?'（未儲存變更）':''),field:$('issue-field').value,category:$('issue-category').value,note:$('issue-note').value});$('issue-dialog').close();$('issue-note').value='';S.word=await api('/api/card/'+S.word.id+'?'+pair());renderInspector();toast('問題已保存在語言資料後台的字卡資料檢查中。');})().catch(error);});
window.addEventListener('beforeunload',e=>{if(S.dirty){e.preventDefault();e.returnValue='';}});
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)||$('issue-dialog')?.open||$('template-dialog')?.open)return;if(e.code==='Space'&&S.word){e.preventDefault();if(S.side==='front')reveal();else{S.side='front';render();}}});
on('template','change',async()=>{const selected=$('template').value;if(S.dirty){await api('/api/templates/save?'+templateQuery(),{layout:S.layout});S.dirty=false;}const result=await api('/api/templates?'+pair()+'&template_id='+encodeURIComponent(selected));S.templates=result;fillTemplates();fillVersions();busy();chooseLayout();await loadExercise();});
on('new-template','click',()=>{$('template-name').value='';$('template-clone').checked=false;$('template-dialog').showModal();$('template-name').focus();});
on('template-cancel','click',()=>$('template-dialog').close());
on('template-form','submit',async e=>{e.preventDefault();const result=await api('/api/templates/create?'+pair(),{name:$('template-name').value,layout:$('template-clone').checked?S.layout:null});S.templates={...result,upstream:S.templates.upstream};fillTemplates();fillVersions();chooseLayout();$('template-dialog').close();toast('新模板已建立，可開始拖曳編排。');});
init();
