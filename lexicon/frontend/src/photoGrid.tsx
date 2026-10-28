import { useEffect, useState } from 'react';
import { api } from './api';
import { ErrorBox, Link, Loading, useLoad } from './ui';

// Photo label table: part of speech (rows) × CEFR level (columns), card #646 (問題回報 #734).
// Built by GET /images/{id}/grid or POST /photo-grid (photo_grid.py). Hover a word: its anchor
// point and box show on the picture, and every word of the same concept lights up.

export type GridWord = { word: string; concept_id: string; anchor: { point: number[]; box: number[] | null }; source: 'photo' | 'lexicon' | 'related'; fit?: number };
export type Grid = { fit_unchecked?: number; rows: string[]; levels: string[]; cells: { pos: string; cefr: string; words: GridWord[] }[] };

const ROW_NAME: Record<string, string> = { verb: '動詞', noun: '名詞', adjective: '形容詞', adverb: '副詞', phrase: '片語' };

/** The picture with the grid under it. */
export function PhotoGridPanel({ src, grid, target, native, title }: { src: string; grid: Grid; target: string; native: string; title: string }) {
  const [hover, setHover] = useState<string | null>(null);
  // The words of the hovered concept: one anchor shared by all of them (photo_grid.py).
  const lit = hover ? grid.cells.flatMap((c) => c.words).filter((w) => w.concept_id === hover) : [];
  const anchor = lit[0]?.anchor;
  return <section className="card" aria-label={title}>
    <h2 style={{ marginTop: 0 }}>{title} <small className="muted">詞性 × CEFR</small></h2>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-start' }}>
      <div style={{ position: 'relative', display: 'inline-block', maxWidth: '100%' }}>
        <img src={src} alt={title} style={{ display: 'block', maxWidth: '100%', maxHeight: 420, borderRadius: 8 }} />
        {anchor?.box && anchor.box.length === 4 && <div aria-hidden style={{
          position: 'absolute', left: `${anchor.box[0] * 100}%`, top: `${anchor.box[1] * 100}%`,
          width: `${(anchor.box[2] - anchor.box[0]) * 100}%`, height: `${(anchor.box[3] - anchor.box[1]) * 100}%`,
          border: '2px dashed var(--accent)', borderRadius: 4, pointerEvents: 'none' }} />}
        {anchor?.point?.length === 2 && <div aria-hidden style={{
          position: 'absolute', left: `${anchor.point[0] * 100}%`, top: `${anchor.point[1] * 100}%`,
          width: 14, height: 14, marginLeft: -7, marginTop: -7, borderRadius: '50%',
          background: 'var(--accent)', border: '2px solid #fff', pointerEvents: 'none' }} />}
      </div>
      <div style={{ flex: '1 1 480px', minWidth: 0, overflowX: 'auto' }}>
        <p className="muted" style={{ margin: '0 0 8px' }}>
          <span className="chip chip-ok">照片看到的</span> <span className="chip chip-info">詞庫同義字</span> <span className="chip chip-warn">詞庫關係網補的（Qwen 檢查過貼題才留）</span>
          {' '}滑過一個字，照片上標出它的位置。
        </p>
        <table aria-label={`${title} 詞性與 CEFR 表格`} style={{ borderCollapse: 'collapse', width: '100%', minWidth: 560 }}>
          <thead><tr><th style={{ textAlign: 'left', padding: 6 }}>詞性</th>{grid.levels.map((l) => <th key={l} style={{ padding: 6 }}>{l}</th>)}</tr></thead>
          <tbody>{grid.rows.map((row) => <tr key={row}>
            <th style={{ textAlign: 'left', padding: 6, verticalAlign: 'top', whiteSpace: 'nowrap' }}>{ROW_NAME[row] ?? row}</th>
            {grid.levels.map((level) => {
              const cell = grid.cells.find((c) => c.pos === row && c.cefr === level);
              return <td key={level} style={{ border: '1px solid var(--line, #ddd)', padding: 6, verticalAlign: 'top', minWidth: 80 }}>
                {(cell?.words ?? []).map((w) => <div key={`${w.concept_id}-${w.word}`} title={w.fit != null ? `Qwen 貼題分數 ${w.fit}` : w.source === 'related' ? 'Qwen 尚未檢查' : undefined} onMouseEnter={() => setHover(w.concept_id)} onMouseLeave={() => setHover(null)}
                  style={{ outline: hover === w.concept_id ? '2px solid var(--accent)' : 'none', borderRadius: 999, margin: '2px 0' }}>
                  <Link to={`/words/${target}/${native}/${encodeURIComponent(w.word)}`} className={`chip ${w.source === 'photo' ? 'chip-ok' : w.source === 'related' ? 'chip-warn' : 'chip-info'}`}>{w.word}</Link>
                </div>)}
              </td>;
            })}
          </tr>)}</tbody>
        </table>
      </div>
    </div>
  </section>;
}

/** A library picture: its grid from the stored labels (GET /images/{id}/grid). */
export function StoredPhotoGrid({ assetId, src, target, native, onClose }: { assetId: number; src: string; target: string; native: string; onClose: () => void }) {
  const grid = useLoad<{ grid: Grid }>(`/images/${assetId}/grid`, [assetId]);
  const [checked, setChecked] = useState<Grid | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const shown = checked ?? grid.data?.grid ?? null;
  // Card #722: one Qwen call judges the related words; verdicts are cached on the server.
  const check = async () => {
    setBusy(true); setErr(null);
    try { setChecked((await api.post<{ grid: Grid }>(`/images/${assetId}/grid/fit`)).grid); } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  return <>
    <div className="toolbar"><button className="btn btn-small" onClick={onClose}>收起表格</button>
      {!!shown?.fit_unchecked && <button className="btn btn-small" disabled={busy} onClick={check}>{busy ? 'Qwen 檢查中…' : `請 Qwen 檢查貼題（${shown.fit_unchecked} 個字）`}</button>}</div>
    {grid.error && <ErrorBox error={grid.error} />}
    {!!err && <ErrorBox error={err instanceof Error ? err.message : String(err)} />}
    {!shown ? <Loading what="讀取標籤表格" /> : <PhotoGridPanel src={src} grid={shown} target={target} native={native} title={`圖片 #${assetId}`} />}
  </>;
}

/** 上傳照片測試: the tagger labels an uploaded picture, then POST /photo-grid builds the table. Nothing is saved. */
export function PhotoUploadTest({ target, native }: { target: string; native: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ src: string; grid: Grid } | null>(null);
  useEffect(() => () => { if (result) URL.revokeObjectURL(result.src); }, [result]);
  const onFile = async (file: File) => {
    setBusy(true); setError('');
    try {
      const tagged = await api.upload<{ tags: unknown[] }>('/photo-grid/tag-upload', file);
      const built = await api.post<{ grid: Grid }>('/photo-grid', { tags: tagged.tags });
      setResult({ src: URL.createObjectURL(file), grid: built.grid });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return <details className="card">
    <summary>上傳照片測試（標籤 → 詞性 × CEFR 表格，不會儲存）</summary>
    <div className="toolbar">
      <input type="file" accept="image/*" aria-label="上傳照片測試" disabled={busy}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) void onFile(f); e.target.value = ''; }} />
      {busy && <span role="status">標籤處理中…（本機視覺模型，可能需要數十秒）</span>}
    </div>
    {error && <ErrorBox error={error} />}
    {result && <PhotoGridPanel src={result.src} grid={result.grid} target={target} native={native} title="上傳的照片" />}
  </details>;
}
