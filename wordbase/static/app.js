'use strict';
// 單字資料庫 — spec-01 section 5 單字管理中心 over the section 6 sources.

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const LETTER = { kaikki: 'K', oewn: 'W', cmudict: 'C', datamuse: 'D', tatoeba: 'T', wordlist: 'L', user: '你' };
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
};

const state = {
  meta: null,
  rows: [],
  selected: new Set(),
  current: store.get('wb-current', null),
  entry: null,
  showEmpty: store.get('wb-show-empty', false),
  covTag: '',
  pending: 0,
};

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || `HTTP ${res.status}`), { data, status: res.status });
  return data;
}

function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 3200);
}

const mark = (source) => `<span class="mark k-${esc(source)}" title="${esc(sourceName(source))}">${esc(LETTER[source] || '?')}</span>`;
const sourceName = (s) => (s === 'user' ? '你的修改' : state.meta?.sources[s]?.name || s);
const rankMark = ['', '①', '②', '③', '④'];

// ── Dialog ────────────────────────────────────────────────────────────

function dialog(html, onSubmit) {
  const dlg = $('#dlg');
  const form = $('#dlg-form');
  form.innerHTML = html;
  return new Promise((resolve) => {
    form.onsubmit = async (e) => {
      const submitter = e.submitter;
      if (!submitter || submitter.value === 'cancel') { resolve(null); return; }
      e.preventDefault();
      try {
        const out = await onSubmit(new FormData(form), submitter.value);
        dlg.close();
        resolve(out ?? true);
      } catch (err) {
        const box = form.querySelector('.err');
        if (box) box.textContent = err.message;
      }
    };
    dlg.onclose = () => resolve(null);
    dlg.showModal();
    form.querySelector('textarea, input:not([type=radio])')?.focus();
  });
}

// ── Meta, filters, list ─────────────────────────────────────────────────

async function loadMeta() {
  state.meta = await api('GET', '/api/meta');
  const fill = (sel, items, first) => {
    const el = $(sel);
    const cur = el.value;
    el.innerHTML = `<option value="">${first}</option>` + items.map(([v, l]) => `<option value="${esc(v)}">${esc(l)}</option>`).join('');
    el.value = items.some(([v]) => v === cur) ? cur : '';
  };
  fill('#f-tag', state.meta.tags.map((t) => [t, t]), '全部標籤');
  fill('#f-level', ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'].map((l) => [l, l]), '全部等級');
  fill('#f-pos', state.meta.pos.map((p) => [p, p]), '全部詞性');
  fill('#f-missing', Object.entries(state.meta.missing), '不限缺漏');
  fill('#f-source', Object.entries(state.meta.sources).map(([k, v]) => [k, `有 ${v.name} 資料`]), '全部來源');
}

function query() {
  const p = new URLSearchParams();
  for (const [id, key] of [['#f-q', 'q'], ['#f-tag', 'tag'], ['#f-level', 'level'], ['#f-pos', 'pos'],
    ['#f-missing', 'missing'], ['#f-source', 'source'], ['#f-sort', 'sort'], ['#f-status', 'status']]) {
    const v = $(id).value.trim();
    if (v) p.set(key, v);
  }
  if ($('#f-dups').checked) p.set('dups', '1');
  return p.toString();
}

async function loadList() {
  const { entries } = await api('GET', '/api/entries?' + query());
  state.rows = entries;
  for (const id of [...state.selected]) if (!entries.some((r) => r.id === id)) state.selected.delete(id);
  renderList();
}

const FLAGS = [['meaning_zh', '中文釋義'], ['ipa', '音標'], ['audio', '真人發音'], ['examples5', '例句 5 句'], ['examples_zh', '繁中例句']];

function renderList() {
  $('#count').textContent = `${state.rows.length} 個單字`;
  $('#list').innerHTML = state.rows.map((r) => {
    const s = r.summary || {};
    const has = s.has || {};
    const dots = FLAGS.map(([k, l]) => `<span class="dot ${has[k] ? 'on' : ''}" title="${esc(l)}${has[k] ? '：有' : '：缺'}"></span>`).join('');
    const pills = [
      r.fetch_status !== 'done' ? `<span class="pill ${esc(r.fetch_status)}">${{ pending: '抓取中', partial: '部分失敗', failed: '失敗' }[r.fetch_status] || ''}</span>` : '',
      r.status === 'archived' ? '<span class="pill archived">已封存</span>' : '',
      r.maybe_duplicate ? '<span class="pill dup">可能重複</span>' : '',
    ].join('');
    const sub = [s.zh, (s.pos || []).join('/'), s.gloss].filter(Boolean).join(' · ');
    return `<div class="row" role="listitem" data-id="${r.id}" aria-current="${r.id === state.current}">
      <input type="checkbox" data-sel="${r.id}" ${state.selected.has(r.id) ? 'checked' : ''} aria-label="選取 ${esc(r.word)}">
      <div style="min-width:0"><div class="w">${esc(r.word)}</div><div class="sub">${esc(sub) || '&nbsp;'}</div></div>
      <div class="right"><span>${pills}${r.extras?.cefr ? `<span class="lv">${esc(r.extras.cefr)}</span>` : ''}</span><span class="dots">${dots}</span></div>
    </div>`;
  }).join('') || '<div class="placeholder">沒有符合的單字</div>';
  renderBatch();
}

function renderBatch() {
  const n = state.selected.size;
  $('#batch').hidden = n === 0;
  $('#batch-n').textContent = `已選 ${n} 個`;
  $('#batch [data-act="merge"]').disabled = n !== 2;
  $('#sel-all').checked = n > 0 && state.rows.every((r) => state.selected.has(r.id));
}

// ── Entry ───────────────────────────────────────────────────────────────

async function openEntry(id) {
  state.current = id;
  store.set('wb-current', id);
  document.querySelectorAll('.row').forEach((el) => el.setAttribute('aria-current', String(Number(el.dataset.id) === id)));
  try {
    state.entry = await api('GET', `/api/entries/${id}`);
  } catch (e) {
    state.entry = null;
    $('#entry').innerHTML = '<div class="placeholder">找不到這個單字</div>';
    return;
  }
  renderEntry();
}

const STATUS = { ok: '有資料', not_found: '查無', error: '錯誤' };

function sourceStatus(e) {
  return Object.entries(state.meta.sources).map(([k, src]) => {
    const r = e.results[k];
    if (!r) return `<span class="ss">${mark(k)}${esc(src.name)}<span class="c">尚未抓取</span></span>`;
    const c = r.counts || {};
    let extra = '';
    if (k === 'tatoeba' && c.sentences !== undefined) extra = `${c.sentences} 句，含中文 ${c.with_mandarin}`;
    if (k === 'kaikki' && c.usage_examples !== undefined) extra = `日常例句 ${c.usage_examples}、書證 ${c.quotations}`;
    if (k === 'oewn' && c.synsets) extra = `${c.synsets} 個詞義`;
    return `<span class="ss ${esc(r.status)}" title="${esc(r.error || '')}">${mark(k)}${esc(src.name)}<span class="c">${esc(STATUS[r.status] || r.status)}${extra ? '・' + esc(extra) : ''}</span></span>`;
  }).join('');
}

function renderValue(key, it) {
  const v = it.value;
  const m = mark(it.source);
  switch (key) {
    case 'senses': {
      const primary = it.primary ? ' primary' : '';
      const only = (state.entry?.view.fields.senses.items.length || 0) < 2;
      const btn = it.primary ? '<span class="trust verified">主要義項</span>'
        : only ? '<span></span>'
          : `<button class="btn small" data-primary="${esc(senseKey(v))}" title="設為主要義項">設為主要</button>`;
      return `<div class="line${primary}">${m}<div><span class="pos">${esc(v.pos)}</span>${esc(v.gloss)}</div>${btn}</div>`;
    }
    case 'meaning_zh':
      return `<span class="chip">${m}${esc(v.trad)}${v.simp && v.simp !== v.trad ? `<span class="t">${esc(v.simp)}</span>` : ''}${v.pos ? `<span class="t">${esc(v.pos)}</span>` : ''}</span>`;
    case 'ipa':
      return `<span class="chip">${m}<span class="ipa-t">${esc(v.ipa)}</span>${(v.accent || []).length ? `<span class="t">${esc(v.accent.slice(0, 2).join(', '))}</span>` : ''}</span>`;
    case 'audio':
      return `<span class="chip">${m}<button class="btn small" data-play="${esc(v.url)}">▶ 播放</button><span class="t">${esc((v.accent || []).slice(0, 2).join(', ') || '口音未標')}</span></span>`;
    case 'homophones':
      return `<span class="chip">${m}${esc(v.word)}<span class="t">${esc(v.type || '')}</span></span>`;
    case 'forms':
      return `<span class="chip">${m}${esc(v.form)}<span class="t">${esc((v.tags || []).join(', '))}</span></span>`;
    case 'morphology':
      return `<span class="chip">${m}${esc((v.parts || []).join(' + '))}</span>`;
    case 'etymology':
      return `<div class="line">${m}<div>${esc(v)}</div><span></span></div>`;
    case 'examples': {
      let zh = '';
      if (v.script === 'Hant') zh = `<span class="zh">${esc(v.translation)}<span class="scr Hant">繁</span></span>`;
      else if (v.translation_tw) zh = `<span class="zh">${esc(v.translation_tw)}<span class="scr conv" title="原文：${esc(v.translation)}">簡→繁</span></span>`;
      else if (v.translation) zh = `<span class="zh">${esc(v.translation)}</span>`;
      else if (it.source === 'tatoeba' || it.source === 'user') zh = '';
      return `<div class="line">${m}<div>${esc(v.text)}${zh}</div><span class="t" style="font-size:11px;color:var(--faint)">${esc(v.license || '')}</span></div>`;
    }
    default:
      return `<span class="chip">${m}${esc(typeof v === 'string' ? v : JSON.stringify(v))}</span>`;
  }
}

const LINE_FIELDS = new Set(['senses', 'etymology', 'examples']);

function senseKey(v) { return `${(v.pos || '').toLowerCase()}|${(v.gloss || '').toLowerCase()}`; }

function fieldBlock(key, f, e) {
  const empty = f.items.length === 0;
  if (empty && !state.showEmpty && f.trust !== 'user') return '';
  const who = f.sources.map((s) => `<span class="src"><i class="k-${esc(s.source)}">${esc(LETTER[s.source])}</i>${rankMark[s.rank]} ${esc(s.name)} ${s.used}${s.found > s.used ? `/${s.found}` : ''}</span>`).join('');
  const trust = f.trust === 'user' ? `<span class="trust user" title="${esc(f.edited_at)}">已修改</span>`
    : f.verified_at ? `<span class="trust verified" title="${esc(f.verified_at)}">已核對</span>` : '';
  const tools = [
    key === 'ipa' ? `<select data-accent aria-label="預設口音"><option value="">預設口音</option>${['US', 'UK'].map((a) => `<option ${e.default_accent === a ? 'selected' : ''}>${a}</option>`).join('')}</select>` : '',
    `<button class="btn small" data-edit="${key}">編輯</button>`,
    f.trust === 'user' ? `<button class="btn small" data-revert="${key}">還原</button>` : '',
    empty ? '' : `<button class="btn small" data-verify="${key}" data-on="${f.verified_at ? 0 : 1}">${f.verified_at ? '取消核對' : '核對'}</button>`,
  ].join('');
  const body = empty
    ? `<div class="empty">沒有來源提供（依序問過：${f.priority.map((p) => esc(p.name)).join('、')}）</div>`
    : LINE_FIELDS.has(key)
      ? `<div class="lines">${f.items.map((it) => renderValue(key, it)).join('')}</div>`
      : `<div class="chips">${f.items.map((it) => renderValue(key, it)).join('')}</div>`;
  const original = f.trust === 'user' && f.original?.length
    ? `<details class="raw"><summary>原始抓取值（${f.original.length}）</summary><div class="${LINE_FIELDS.has(key) ? 'lines' : 'chips'}">${f.original.map((it) => renderValue(key, it)).join('')}</div></details>` : '';
  return `<div class="field"><div class="fhead"><span class="name">${esc(f.label)}</span><span class="who">${who}</span>${trust}<span class="tools">${tools}</span></div>${body}${original}</div>`;
}

function renderEntry() {
  const e = state.entry;
  if (!e) return;
  const fields = e.view.fields || {};
  const ipa = fields.ipa?.items?.[0]?.value?.ipa;
  const x = e.extras || {};
  const facts = [
    x.cefr ? `<span class="fact">等級 <b>${esc(x.cefr)}</b>（CEFR-J）</span>` : '',
    x.zipf !== undefined ? `<span class="fact">使用頻率 <b>${esc(x.zipf)}</b> Zipf</span>` : '',
    `<span class="fact">抓取 <b>${esc({ pending: '進行中', done: '完成', partial: '部分失敗', failed: '失敗' }[e.fetch_status])}</b>${e.fetched_at ? ' · ' + esc(e.fetched_at.slice(0, 16).replace('T', ' ')) : ''}</span>`,
    `<span class="fact">照片 <b>${e.photo_refs}</b> · 卡片 <b>${e.card_refs}</b></span>`,
  ].join('');
  const groups = state.meta.groups.map((g) => {
    const blocks = Object.entries(fields).filter(([, f]) => f.group === g).map(([k, f]) => fieldBlock(k, f, e)).join('');
    return blocks ? `<section class="group"><h3>${esc(g)}</h3>${blocks}</section>` : '';
  }).join('');
  $('#entry').innerHTML = `<div class="entry">
    <div class="ehead">
      <div><h2>${esc(e.word)}${ipa ? `<span class="ipa">${esc(ipa)}</span>` : ''}</h2><div class="facts">${facts}</div></div>
      <div class="actions">
        <label class="check"><input type="checkbox" id="show-empty" ${state.showEmpty ? 'checked' : ''}> 顯示空白欄位</label>
        <button class="btn" data-refetch>重新抓取</button>
        <button class="btn" data-archive>${e.status === 'archived' ? '復原' : '封存'}</button>
        <button class="btn danger" data-delete>刪除</button>
      </div>
    </div>
    <div class="tags">${e.tags.map((t) => `<span class="tag">${esc(t)}<button data-untag="${esc(t)}" aria-label="移除標籤 ${esc(t)}">×</button></span>`).join('')}<input id="tag-in" placeholder="＋ 標籤" aria-label="新增標籤"></div>
    ${e.fetch_error ? `<div class="ss error">${esc(e.fetch_error)}</div>` : ''}
    <div class="srcstatus">${sourceStatus(e)}</div>
    ${groups || '<div class="placeholder">還沒有資料，抓取中…</div>'}
  </div>`;
}

// ── Editing (原始值會保留) ───────────────────────────────────────────────

const FORMAT = {
  senses: ['詞性 | 定義', (v) => `${v.pos} | ${v.gloss}`, ([pos, gloss]) => ({ pos: pos || '', gloss: gloss ?? pos })],
  meaning_zh: ['繁體 | 詞性', (v) => `${v.trad}${v.pos ? ' | ' + v.pos : ''}`, ([trad, pos]) => ({ trad, simp: trad, pos: pos || '' })],
  ipa: ['/IPA/ | 口音', (v) => `${v.ipa}${(v.accent || []).length ? ' | ' + v.accent.join(', ') : ''}`, ([ipa, acc]) => ({ ipa, accent: acc ? acc.split(/,\s*/) : [] })],
  audio: ['音檔網址 | 口音', (v) => `${v.url}${(v.accent || []).length ? ' | ' + v.accent.join(', ') : ''}`, ([url, acc]) => ({ url, accent: acc ? acc.split(/,\s*/) : [] })],
  homophones: ['單字 | 同音／近音', (v) => `${v.word} | ${v.type || '同音'}`, ([word, type]) => ({ word, type: type || '同音' })],
  forms: ['詞形 | 標記', (v) => `${v.form} | ${(v.tags || []).join(', ')}`, ([form, tags]) => ({ form, tags: tags ? tags.split(/,\s*/) : [] })],
  morphology: ['字根 + 字尾', (v) => (v.parts || []).join(' + '), ([s]) => ({ parts: s.split('+').map((p) => p.trim()).filter(Boolean), kind: 'user' })],
  examples: ['英文例句 | 中文翻譯', (v) => `${v.text}${v.translation_tw || v.translation ? ' | ' + (v.script === 'Hant' ? v.translation : v.translation_tw || v.translation) : ''}`, ([text, zh]) => (zh ? { text, translation: zh, script: 'Hant' } : { text })],
};

async function editField(key) {
  const f = state.entry.view.fields[key];
  const [hint, toLine, fromParts] = FORMAT[key] || ['一行一個', (v) => (typeof v === 'string' ? v : JSON.stringify(v)), ([s]) => s];
  const text = f.items.map((it) => toLine(it.value)).join('\n');
  await dialog(`<h3>編輯「${esc(f.label)}」</h3>
    <div class="hint">一行一項，格式：${esc(hint)}。你的修改會蓋過抓取的值，原始值仍保留，可以隨時還原。</div>
    <textarea name="v" aria-label="${esc(f.label)}">${esc(text)}</textarea>
    <div class="err hint" style="color:var(--bad)"></div>
    <div class="row2"><button class="btn" value="cancel" formnovalidate>取消</button><button class="btn primary" value="ok">儲存</button></div>`,
  async (fd) => {
    const value = String(fd.get('v')).split('\n').map((l) => l.trim()).filter(Boolean)
      .map((l) => fromParts(l.split('|').map((p) => p.trim())));
    state.entry = await api('PUT', `/api/entries/${state.entry.id}/fields/${key}`, { value });
    renderEntry();
    loadList();
  });
}

// ── Events ──────────────────────────────────────────────────────────────

let audio;
$('#entry').addEventListener('click', async (ev) => {
  const t = ev.target.closest('button');
  if (!t || !state.entry) return;
  const id = state.entry.id;
  if (t.dataset.play) {
    audio?.pause();
    audio = new Audio(t.dataset.play);
    audio.play().catch(() => toast('無法播放這個音檔'));
  } else if (t.dataset.edit) {
    editField(t.dataset.edit);
  } else if (t.dataset.revert) {
    state.entry = await api('DELETE', `/api/entries/${id}/fields/${t.dataset.revert}`);
    renderEntry(); loadList(); toast('已還原成抓取的值');
  } else if (t.dataset.verify) {
    state.entry = await api('POST', `/api/entries/${id}/fields/${t.dataset.verify}/verify`, { verified: t.dataset.on === '1' });
    renderEntry();
  } else if (t.dataset.primary) {
    state.entry = await api('PATCH', `/api/entries/${id}`, { primary_sense: t.dataset.primary });
    renderEntry(); loadList();
  } else if (t.dataset.untag !== undefined) {
    state.entry = await api('PATCH', `/api/entries/${id}`, { tags: state.entry.tags.filter((x) => x !== t.dataset.untag) });
    renderEntry(); loadMeta(); loadList();
  } else if ('refetch' in t.dataset) {
    await api('POST', `/api/entries/${id}/refetch`);
    toast('重新抓取中'); poll();
  } else if ('archive' in t.dataset) {
    state.entry = await api('PATCH', `/api/entries/${id}`, { status: state.entry.status === 'archived' ? 'active' : 'archived' });
    renderEntry(); loadList();
  } else if ('delete' in t.dataset) {
    confirmDelete([state.entry]);
  }
});
$('#entry').addEventListener('change', async (ev) => {
  if (ev.target.id === 'show-empty') {
    state.showEmpty = ev.target.checked;
    store.set('wb-show-empty', state.showEmpty);
    renderEntry();
  } else if ('accent' in ev.target.dataset) {
    state.entry = await api('PATCH', `/api/entries/${state.entry.id}`, { default_accent: ev.target.value || null });
    renderEntry();
  }
});
$('#entry').addEventListener('keydown', async (ev) => {
  if (ev.target.id !== 'tag-in' || ev.key !== 'Enter') return;
  const tag = ev.target.value.trim();
  if (!tag) return;
  state.entry = await api('PATCH', `/api/entries/${state.entry.id}`, { tags: [...state.entry.tags, tag] });
  renderEntry(); loadMeta(); loadList();
  $('#tag-in')?.focus();
});

$('#list').addEventListener('click', (ev) => {
  const box = ev.target.closest('input[data-sel]');
  if (box) {
    const id = Number(box.dataset.sel);
    box.checked ? state.selected.add(id) : state.selected.delete(id);
    renderBatch();
    return;
  }
  const row = ev.target.closest('.row');
  if (row) openEntry(Number(row.dataset.id));
});
$('#sel-all').addEventListener('change', (ev) => {
  state.rows.forEach((r) => (ev.target.checked ? state.selected.add(r.id) : state.selected.delete(r.id)));
  renderList();
});

let debounce;
for (const id of ['#f-q', '#f-tag', '#f-level', '#f-pos', '#f-missing', '#f-source', '#f-sort', '#f-status', '#f-dups']) {
  $(id).addEventListener(id === '#f-q' ? 'input' : 'change', () => { clearTimeout(debounce); debounce = setTimeout(loadList, 150); });
}

async function confirmDelete(entries) {
  const full = await Promise.all(entries.map((e) => (e.photo_refs !== undefined ? e : api('GET', `/api/entries/${e.id}`))));
  const photos = full.reduce((n, e) => n + e.photo_refs, 0);
  const cards = full.reduce((n, e) => n + e.card_refs, 0);
  const blocked = photos + cards > 0;
  await dialog(`<h3>刪除 ${full.length === 1 ? `「${esc(full[0].word)}」` : `${full.length} 個單字`}？</h3>
    <div class="hint">影響：${photos} 張照片、${cards} 張卡片。${blocked ? '仍有照片或卡片引用的單字不能直接刪除，可以改成封存。' : '刪除後無法復原；只想先收起來可以改用封存。'}</div>
    <div class="row2"><button class="btn" value="cancel" formnovalidate>取消</button><button class="btn" value="archive">改成封存</button>${blocked ? '' : '<button class="btn primary" value="delete">刪除</button>'}</div>`,
  async (_, action) => {
    const ids = full.map((e) => e.id);
    const res = await api('POST', '/api/batch', { ids, action });
    if (res.blocked?.length) toast(`${res.blocked.join('、')} 仍有引用，沒有刪除`);
    else toast(action === 'delete' ? '已刪除' : '已封存');
    if (ids.includes(state.current) && action === 'delete') { state.entry = null; $('#entry').innerHTML = '<div class="placeholder">選一個單字看完整資料</div>'; }
    state.selected.clear();
    await loadList();
    if (state.entry) openEntry(state.entry.id);
  });
}

$('#batch').addEventListener('click', async (ev) => {
  const act = ev.target.closest('button')?.dataset.act;
  if (!act) return;
  const ids = [...state.selected];
  if (act === 'delete') return confirmDelete(ids.map((id) => ({ id })));
  if (act === 'merge') {
    const [a, b] = ids.map((id) => state.rows.find((r) => r.id === id));
    return dialog(`<h3>合併重複單字</h3>
      <div class="hint">保留哪一個？另一個的標籤、你的修改和它有、保留者沒有的來源資料會併進來；照片情境與卡片在學習 App 裡各自保留（規格第 5 節）。</div>
      <label class="check"><input type="radio" name="t" value="${a.id}" checked> 保留「${esc(a.word)}」</label>
      <label class="check"><input type="radio" name="t" value="${b.id}"> 保留「${esc(b.word)}」</label>
      <div class="err hint" style="color:var(--bad)"></div>
      <div class="row2"><button class="btn" value="cancel" formnovalidate>取消</button><button class="btn primary" value="ok">合併</button></div>`,
    async (fd) => {
      const target = Number(fd.get('t'));
      const other = target === a.id ? b.id : a.id;
      await api('POST', '/api/merge', { target, other });
      state.selected.clear();
      toast('已合併');
      await loadList();
      openEntry(target);
    });
  }
  if (act === 'tag' || act === 'untag') {
    return dialog(`<h3>${act === 'tag' ? '加上標籤' : '移除標籤'}（${ids.length} 個單字）</h3>
      <input name="tag" list="tag-list" placeholder="標籤名稱" required aria-label="標籤">
      <datalist id="tag-list">${state.meta.tags.map((t) => `<option value="${esc(t)}">`).join('')}</datalist>
      <div class="err hint" style="color:var(--bad)"></div>
      <div class="row2"><button class="btn" value="cancel" formnovalidate>取消</button><button class="btn primary" value="ok">套用</button></div>`,
    async (fd) => {
      await api('POST', '/api/batch', { ids, action: act, tag: fd.get('tag') });
      await loadMeta(); await loadList();
      if (state.entry && ids.includes(state.entry.id)) openEntry(state.entry.id);
    });
  }
  await api('POST', '/api/batch', { ids, action: act });
  toast({ refetch: '重新抓取中', archive: '已封存', restore: '已復原' }[act] || '完成');
  if (act === 'refetch') poll();
  await loadList();
  if (state.entry && ids.includes(state.entry.id)) openEntry(state.entry.id);
});

$('#add').addEventListener('click', () => dialog(`<h3>新增單字</h3>
  <div class="hint">一行一個（或用逗號分開），片語也可以。新增後會依規格第 6 節的來源順位在背景抓取。</div>
  <textarea name="words" placeholder="apple&#10;pine nuts&#10;on the table" aria-label="單字"></textarea>
  <input name="tags" placeholder="標籤（可不填，用逗號分開）" aria-label="標籤">
  <div class="err hint" style="color:var(--bad)"></div>
  <div class="row2"><button class="btn" value="cancel" formnovalidate>取消</button><button class="btn primary" value="ok">新增並抓取</button></div>`,
async (fd) => {
  const tags = String(fd.get('tags') || '').split(',').map((t) => t.trim()).filter(Boolean);
  const res = await api('POST', '/api/entries', { words: String(fd.get('words') || ''), tags });
  toast(`新增 ${res.created.length} 個${res.duplicates.length ? `，已存在 ${res.duplicates.length} 個（${res.duplicates.slice(0, 3).join('、')}${res.duplicates.length > 3 ? '…' : ''}）` : ''}`);
  await loadMeta(); await loadList();
  if (res.created[0]) openEntry(res.created[0]);
  poll();
}));

// ── Coverage view ───────────────────────────────────────────────────────

async function renderCoverage() {
  const p = new URLSearchParams({ status: 'active' });
  if (state.covTag) p.set('tag', state.covTag);
  const c = await api('GET', '/api/coverage?' + p);
  const pct = (n) => (c.total ? Math.round((100 * n) / c.total) : 0);
  const targetLabels = { meaning_zh: '有中文釋義', ipa: '有音標', audio: '有真人發音', examples5: '例句 ≥ 5 句', examples_zh: '有繁中翻譯例句', synonyms: '有近義字', forms: '有詞形變化', morphology: '有字根字尾' };
  let lastGroup = '';
  const rows = c.fields.map((f) => {
    const grp = f.group !== lastGroup ? `<tr class="grp"><td colspan="5">${esc(f.group)}</td></tr>` : '';
    lastGroup = f.group;
    const cells = [0, 1, 2].map((i) => {
      const cell = f.cells[i];
      if (!cell) return '<td></td>';
      const p2 = pct(cell.found);
      return `<td><div class="bar"><span class="mark k-${esc(cell.source)}">${esc(LETTER[cell.source])}</span><span class="track"><span class="fill k-${esc(cell.source)}" style="width:${p2}%;display:block"></span></span><span class="p">${p2}%</span><span class="nm">${rankMark[cell.rank]} ${esc(sourceName(cell.source))} · ${cell.found}/${c.total}</span></div></td>`;
    }).join('');
    return `${grp}<tr><th scope="row">${esc(f.label)}</th>${cells}<td class="anyp">${pct(f.any)}%</td></tr>`;
  }).join('');
  const status = Object.entries(c.status).map(([s, st]) => `<span class="ss">${mark(s)}${esc(sourceName(s))}<span class="c">有資料 ${st.ok || 0}・查無 ${st.not_found || 0}${st.error ? `・錯誤 ${st.error}` : ''}</span></span>`).join('');
  $('#view-cov').innerHTML = `
    <h2>來源能抓到多少？</h2>
    <p class="note">每個單字都問過規格第 6 節列出的每個來源。長條是「該來源有提供這項資料的單字比例」，①②③ 是規格的首選、次選、補充；最右欄是任一來源有資料的比例。「拼字相近」的首選 Kaikki 字表需要 3 GB 的完整資料檔，這裡以 CMUdict＋CEFR-J 字表比對代替。</p>
    <div class="gchips">${['', ...state.meta.tags].map((t) => `<button class="gchip" data-cov="${esc(t)}" aria-pressed="${t === state.covTag}">${esc(t || '全部')}</button>`).join('')}</div>
    <div class="targets">${Object.entries(c.targets).map(([k, n]) => `<div class="target"><div class="v">${pct(n)}%</div><div class="l">${esc(targetLabels[k] || k)}（${n}/${c.total}）</div></div>`).join('')}</div>
    <div class="srcstatus">${status}</div>
    <div class="tablewrap"><table class="m"><thead><tr><th>資料</th><th>首選</th><th>次選</th><th>補充</th><th>任一來源</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
$('#view-cov').addEventListener('click', (ev) => {
  const b = ev.target.closest('[data-cov]');
  if (!b) return;
  state.covTag = b.dataset.cov;
  renderCoverage();
});

function showTab(which) {
  const words = which === 'words';
  $('#tab-words').setAttribute('aria-selected', String(words));
  $('#tab-cov').setAttribute('aria-selected', String(!words));
  $('#view-words').hidden = !words;
  $('#view-cov').hidden = words;
  if (!words) renderCoverage();
}
$('#tab-words').addEventListener('click', () => showTab('words'));
$('#tab-cov').addEventListener('click', () => showTab('cov'));

// ── Background fetch status ────────────────────────────────────────────

let pollTimer;
async function poll() {
  clearTimeout(pollTimer);
  try {
    const s = await api('GET', '/api/status');
    const busy = s.pending > 0;
    $('#stat').innerHTML = busy
      ? `<span class="spin" aria-hidden="true"></span>抓取中 <b>${s.pending}</b> 個 · 共 <b>${s.total}</b> 個單字`
      : `共 <b>${s.total}</b> 個單字`;
    if (busy || state.pending !== s.pending) {
      if (state.pending !== s.pending) {
        await loadList();
        if (!$('#view-cov').hidden) renderCoverage();
        if (state.entry && state.entry.fetch_status === 'pending') openEntry(state.entry.id);
      }
      state.pending = s.pending;
    }
    pollTimer = setTimeout(poll, busy ? 2000 : 15000);
  } catch (e) {
    $('#stat').textContent = '連不到資料庫伺服器';
    pollTimer = setTimeout(poll, 5000);
  }
}

(async function start() {
  await loadMeta();
  await loadList();
  const first = state.rows.find((r) => r.id === state.current) || state.rows[0];
  if (first) openEntry(first.id);
  poll();
})();
