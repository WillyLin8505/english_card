import { useState } from "react";
import { Empty, ErrorBox, Link, Loading, PairPicker, Rate, useApp, useLoad } from "../ui";

type Cov = {
  total_words: number;
  full_words: number;
  stub_words: number;
  fields_only_words: number;
  resolved_words: number;
  matched: number;
  words: { lemma: string; status: string; has_fields: boolean; target: [number, number]; native: [number, number]; failed: number; missing: number; override: number }[];
  fields: { field: string; label: string; block: string; scope: string; counts: Record<string, number>; rate: number | null }[];
};

export default function Coverage() {
  const { target, native, langName, meta } = useApp();
  return <Database key={`${target}/${native}`} target={target} native={native} langName={langName} meta={meta} />;
}

function Database({ target, native, langName, meta }: Pick<ReturnType<typeof useApp>, "target" | "native" | "langName" | "meta">) {
  const [q, setQ] = useState("");
  const [only, setOnly] = useState("");
  const [view, setView] = useState<"words" | "fields">("words");
  const [offset, setOffset] = useState(0);
  const limit = 100;
  const cov = useLoad<Cov>(`/coverage/${target}/${native}?limit=${limit}&offset=${offset}${q ? `&q=${encodeURIComponent(q)}` : ""}${only ? `&only=${only}` : ""}`, [target, native, q, only, offset]);
  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>單字資料庫（Word Database）</h1>
          <p className="muted">所有已建詞條與關聯詞；點單字看詞義、例句與相關詞。關聯詞尚待擷取，不代表已有完整釋義。</p>
        </div>
        <div><Link to="/bulk-add" className="btn">批量加入單字</Link> <PairPicker /></div>
      </header>
      <div className="toolbar">
        <input className="input" placeholder="搜尋單字" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} aria-label="搜尋單字" />
        <select value={only} onChange={(e) => { setOnly(e.target.value); setOffset(0); }} aria-label="篩選">
          <option value="">全部</option>
          <option value="full">已建詞條</option>
          <option value="stub">僅關聯、待擷取</option>
          <option value="not_run">此語言方向尚未擷取</option>
          <option value="incomplete">有缺少或失敗</option>
          <option value="failed">有失敗</option>
        </select>
        <div className="seg">
          <button className={view === "words" ? "on" : ""} onClick={() => setView("words")}>依單字</button>
          <button className={view === "fields" ? "on" : ""} onClick={() => setView("fields")}>依欄位</button>
        </div>
      </div>
      {view === "fields" && <p className="muted">以下統計此語言方向所有已擷取欄位，不受單字篩選影響；待擷取詞不計入完整率。</p>}
      {cov.error && <ErrorBox error={cov.error} onRetry={() => cov.reload()} />}
      {!cov.data ? (
        <Loading />
      ) : cov.data.total_words === 0 ? (
        <Empty>
          {langName(target)}→{langName(native)} 還沒有資料。<Link to="/imports/new">建立擷取工作</Link>。
        </Empty>
      ) : view === "words" ? (
        <>
          <p className="muted">
            {q || only ? `${cov.data.matched} / ${cov.data.total_words}` : cov.data.total_words} 個唯一單字
            （不同詞性只計一次）；已建詞條 {cov.data.full_words}、僅關聯 {cov.data.stub_words}、此語言方向有擷取紀錄 {cov.data.resolved_words}。
            {cov.data.fields_only_words > 0 && `另有 ${cov.data.fields_only_words} 個只有擷取紀錄、尚未建立詞條。`}
          </p>
          <div className="toolbar" aria-label="單字分頁">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>上一頁</button>
            <span>{cov.data.matched ? offset + 1 : 0}–{Math.min(offset + cov.data.words.length, cov.data.matched)} / {cov.data.matched}</span>
            <button disabled={offset + limit >= cov.data.matched} onClick={() => setOffset(offset + limit)}>下一頁</button>
          </div>
          <table className="table">
            <thead>
              <tr><th>單字</th><th>資料狀態</th><th>{langName(target)} 欄位</th><th>{langName(native)} 欄位</th><th>缺少</th><th>失敗</th><th>覆寫</th></tr>
            </thead>
            <tbody>
              {cov.data.words.map((w) => (
                <tr key={w.lemma}>
                  <td><Link to={`/words/${target}/${native}/${encodeURIComponent(w.lemma)}`}>{w.lemma}</Link></td>
                  <td>{w.status === "full" ? "已建詞條" : w.status === "stub" ? "僅關聯、待擷取" : "僅擷取紀錄"}{!w.has_fields && <small className="muted">（此方向尚未擷取）</small>}</td>
                  <td><Rate value={w.target[1] ? w.target[0] / w.target[1] : null} /> <small className="muted">{w.target[0]}/{w.target[1]}</small></td>
                  <td><Rate value={w.native[1] ? w.native[0] / w.native[1] : null} /> <small className="muted">{w.native[0]}/{w.native[1]}</small></td>
                  <td className={w.missing ? "warn" : ""}>{w.missing}</td>
                  <td className={w.failed ? "bad" : ""}>{w.failed}</td>
                  <td>{w.override || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <table className="table">
          <thead>
            <tr><th>區塊</th><th>欄位</th><th>範圍</th><th>完整率</th><th>完成</th><th>部分</th><th>缺值</th><th>失敗</th><th>未設定</th><th></th></tr>
          </thead>
          <tbody>
            {cov.data.fields.map((f) => (
              <tr key={f.field}>
                <td>{meta.blocks.find((b) => b.key === f.block)?.label}</td>
                <td>{f.label}</td>
                <td><span className={`scope scope-${f.scope}`}>{f.scope === "native" ? "母語" : "目標"}</span></td>
                <td><Rate value={f.rate} /></td>
                <td>{(f.counts.complete ?? 0) + (f.counts.user_override ?? 0)}</td>
                <td className="warn">{f.counts.partial ?? 0}</td>
                <td className="warn">{f.counts.missing ?? 0}</td>
                <td className="bad">{f.counts.failed ?? 0}</td>
                <td>{f.counts.unset ?? 0}</td>
                <td><Link to={`/policies?field=${f.field}`}>順位</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
