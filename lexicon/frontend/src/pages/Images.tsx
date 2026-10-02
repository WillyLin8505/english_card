import { useMemo, useState } from 'react';
import { api } from '../api';
import { ErrorBox, Link, Loading, TagScores, useLoad } from '../ui';

type Sense = { id: number; lemma: string; pos: string; translation: string | null };
type Candidate = { id: number; title: string; description: string; author: string; license_code: string; page_url: string; imported: boolean };
type Asset = {
  id: number; sense_id: number; review_status: string; semantic_score: number | null; role: string;
  ordinal: number; lemma: string; normalized: string; pos: string; gloss: string | null; native: string | null;
  asset_id: number; author: string; license_code: string; page_url: string; width: number; height: number;
  size_bytes: number; status: string; tag_status: string; tag_count: number; shared: number;
  tags: { word: string; pos: string | null; score?: number | null }[];
  dropped_tags: { word: string; pos: string | null; score?: number | null }[];
};


const STATUS: Record<string, string> = { approved: '已核准', rejected: '已拒絕', pending: '待審核' };

/** Image Library & Review (spec 08): pictures by word and sense, with their
 *  semantic score, licence and duplicate state; approve, reject, move to
 *  another sense, make representative, or search a word's pictures again. */
export default function Images() {
  const senses = useLoad<Sense[]>('/images/senses', []);
  const library = useLoad<Asset[]>('/images', []);
  const [only, setOnly] = useState<'pending' | 'all'>('pending');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const run = async (fn: () => Promise<string>) => {
    setBusy(true); setError(''); setMessage('');
    try { setMessage(await fn()); library.reload(true); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const words = useMemo(() => {
    const byWord = new Map<string, Map<number, Asset[]>>();
    for (const a of library.data ?? []) {
      if (only === 'pending' && a.review_status !== 'pending') continue;
      const w = byWord.get(a.normalized) ?? new Map<number, Asset[]>();
      w.set(a.sense_id, [...(w.get(a.sense_id) ?? []), a]);
      byWord.set(a.normalized, w);
    }
    return [...byWord.entries()];
  }, [library.data, only]);
  const pending = library.data?.filter((a) => a.review_status === 'pending') ?? [];
  const top = pending.filter((a) => (a.semantic_score ?? 0) >= 0.95).length;
  const sensesOf = (lemma: string) => (senses.data ?? []).filter((x) => x.lemma.toLowerCase() === lemma);

  return <div className="page page-wide">
    <header className="page-head"><div><h1>圖片庫與審核</h1>
      <p className="muted">擷取工作會自動為名詞的前兩個詞義抓圖，每張圖再由本機視覺模型打上標籤。圖片的 AI 標籤必須認出這個字才能核准；沒認出的會自動拒絕，不會放在這個字下面。只有核准的圖片會顯示在單字頁並進入資料包。語意分數：0.95 AI 標籤認出這個字、0.9 Wikidata 概念代表圖、0.7 檔名或說明提到這個字。每個 AI 標籤後面的百分比是它的辨識分數：模型再看一次圖片、逐一確認標籤時回答「有出現」的機率。<strong>只有 80% 以上的標籤通過</strong>，才會用來認字、分享到其他單字與顯示在圖片上；未通過的收在每張圖下方。</p></div></header>
    {error && <ErrorBox error={error} />}{library.error && <ErrorBox error={library.error} />}
    {message && <p role="status">{message}</p>}
    <div className="toolbar">
      <label><input type="radio" checked={only === 'pending'} onChange={() => setOnly('pending')} /> 待審核（{pending.length}）</label>
      <label><input type="radio" checked={only === 'all'} onChange={() => setOnly('all')} /> 全部（{library.data?.length ?? 0}）</label>
      {top > 0 && <button className="btn btn-primary" disabled={busy} onClick={() => run(async () => {
        const r = await api.post<{ approved: number }>('/images/review-batch', { min_score: 0.95, note: '管理者批次核准 AI 認出該字的圖片' });
        return `已核准 ${r.approved} 張 AI 認出該字的圖片。`;
      })}>核准 AI 認出該字的圖片（{top} 張）</button>}
    </div>
    {!library.data ? <Loading /> : words.length === 0 ? <p className="muted">{only === 'pending' ? '沒有待審核的圖片。' : '尚未儲存圖片。'}</p> : words.map(([lemma, bySense]) => (
      <section key={lemma} className="card">
        <div className="toolbar" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}><Link to={`/words/en/zh-TW/${encodeURIComponent(lemma)}`}>{lemma}</Link></h2>
          <button className="btn" disabled={busy} onClick={() => run(async () => {
            const r = await api.post<{ dropped: number; images: number }>('/images/refetch', { lemma });
            return `「${lemma}」重新搜尋：移除 ${r.dropped} 張待審核，下載 ${r.images} 張新候選。`;
          })}>重新搜尋這個字的圖片</button>
        </div>
        {[...bySense.entries()].map(([senseId, list]) => (
          <div key={senseId}>
            <h3>{list[0].pos} #{list[0].ordinal + 1} {list[0].native ?? ''} <small className="muted">{list[0].gloss ?? ''}</small></h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))', gap: 16 }}>
              {list.map((a) => (
                <article className="card" key={a.id} style={{ padding: 14 }}>
                  <img src={`/api/images/${a.asset_id}/file`} alt={`${a.lemma} 詞義 ${a.ordinal + 1} 的候選圖片`} style={{ width: '100%', height: 190, objectFit: 'cover', borderRadius: 8 }} />
                  <p>{STATUS[a.review_status] ?? a.review_status}{a.role === 'representative' ? ' · 代表圖' : ''} · 語意分數 {a.semantic_score ?? '—'}
                    {' · '}{a.tag_status === 'done' ? `AI 標籤 ${a.tag_count} 個` : a.tag_status === 'failed' ? 'AI 標籤失敗'
                      : a.tag_count > 0 ? `AI 標籤 ${a.tag_count} 個（已評分；不足 8 個，稍後再補看）` : 'AI 標籤處理中'}
                    {a.shared > 0 && <span className="warn"> · 重複：另有 {a.shared} 個詞義使用</span>}</p>
                  <TagScores tags={a.tags} word={a.normalized} />
                  {a.dropped_tags?.length > 0 && <details>
                    <summary className="muted">未通過的標籤（辨識分數 &lt; 80%）{a.dropped_tags.length} 個</summary>
                    <TagScores tags={a.dropped_tags} word={a.normalized} label="未通過的 AI 標籤" />
                  </details>}
                  <p className="muted" style={{ overflowWrap: 'anywhere' }}>{a.width} × {a.height} · {a.license_code} · {a.author?.slice(0, 80)} · <a href={a.page_url} target="_blank" rel="noreferrer">來源頁 ↗</a></p>
                  <div className="toolbar">
                    <button className="btn btn-small" disabled={busy || a.review_status === 'approved'} onClick={() => run(async () => { await api.post(`/images/${a.id}/approve`, {}); return '已核准。'; })}>核准</button>
                    <button className="btn btn-small" disabled={busy || a.review_status === 'rejected'} onClick={() => run(async () => { await api.post(`/images/${a.id}/reject`, {}); return '已拒絕。'; })}>拒絕</button>
                    <button className="btn btn-small" disabled={busy || a.role === 'representative'} onClick={() => run(async () => { await api.post(`/images/${a.id}/representative`); return '已設為代表圖。'; })}>設為代表圖</button>
                    <select aria-label="改綁詞義" disabled={busy} value="" onChange={(e) => {
                      const to = Number(e.target.value);
                      if (to) run(async () => { await api.post(`/images/${a.id}/rebind`, { sense_id: to }); return '已改綁詞義，請在新詞義下重新審核。'; });
                    }}>
                      <option value="">改綁詞義…</option>
                      {sensesOf(a.normalized).filter((x) => x.id !== a.sense_id).map((x) => <option key={x.id} value={x.id}>{x.pos} #{x.id} {x.translation ?? ''}</option>)}
                    </select>
                  </div>
                </article>
              ))}
            </div>
          </div>
        ))}
      </section>
    ))}
    <ManualSearch senses={senses.data ?? []} onImported={() => library.reload(true)} />
  </div>;
}

/** A sense with no picture found automatically: search a Wikidata concept by hand. */
function ManualSearch({ senses, onImported }: { senses: Sense[]; onImported: () => void }) {
  const [sense, setSense] = useState('');
  const [qid, setQid] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const run = async (fn: () => Promise<void>) => { setBusy(true); setNote(''); try { await fn(); } catch (e) { setNote((e as Error).message); } finally { setBusy(false); } };
  return <details className="card"><summary>手動指定 Wikidata 概念搜尋圖片</summary>
    <div className="toolbar">
      <label>對應詞義 <select aria-label="對應詞義" value={sense} onChange={(e) => { setSense(e.target.value); setCandidates([]); }} disabled={busy} style={{ maxWidth: 430 }}><option value="">選擇單字與詞義</option>{senses.map((s) => <option key={s.id} value={s.id}>{s.lemma} · {s.pos} · #{s.id} {s.translation || '翻譯待補'}</option>)}</select></label>
      <label>Wikidata 概念 <input aria-label="Wikidata 概念" className="input" value={qid} onChange={(e) => { setQid(e.target.value); setCandidates([]); }} disabled={busy} placeholder="例如 Q89" /></label>
      <button className="btn" disabled={busy || !sense || !qid} onClick={() => run(async () => { const r = await api.post<{ candidates: Candidate[]; concept: string }>('/images/search', { sense_id: Number(sense), qid }); setCandidates(r.candidates); setNote(`概念：${r.concept}，找到 ${r.candidates.length} 張符合授權的候選圖片。`); })}>{busy ? '處理中…' : '搜尋圖片'}</button>
    </div>
    {note && <p role="status">{note}</p>}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(240px,1fr))', gap: 12 }}>{candidates.map((c) => <article key={c.id} className="card" style={{ padding: 12, overflowWrap: 'anywhere' }}><strong>{c.title}</strong><p>{c.license_code} · {c.author.slice(0, 80)}</p><a href={c.page_url} target="_blank" rel="noreferrer">原始圖片 ↗</a><p><button className="btn btn-small" disabled={busy || c.imported} onClick={() => run(async () => { await api.post(`/images/candidates/${c.id}/import`, {}); setCandidates((old) => old.map((x) => (x.id === c.id ? { ...x, imported: true } : x))); onImported(); })}>{c.imported ? '已下載' : '下載到詞庫'}</button></p></article>)}</div>
  </details>;
}
