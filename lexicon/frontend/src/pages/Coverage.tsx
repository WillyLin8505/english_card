import { useState } from "react";
import { Empty, ErrorBox, Link, Loading, PairPicker, Rate, useApp, useLoad } from "../ui";

type Cov = {
  total_words: number;
  matched: number;
  words: { lemma: string; target: [number, number]; native: [number, number]; failed: number; missing: number; override: number }[];
  fields: { field: string; label: string; block: string; scope: string; counts: Record<string, number>; rate: number | null }[];
};

export default function Coverage() {
  const { target, native, langName, meta } = useApp();
  const [q, setQ] = useState("");
  const [only, setOnly] = useState("");
  const [view, setView] = useState<"words" | "fields">("words");
  const cov = useLoad<Cov>(`/coverage/${target}/${native}?limit=500${q ? `&q=${encodeURIComponent(q)}` : ""}${only ? `&only=${only}` : ""}`, [target, native, q, only]);
  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>單字覆蓋率（Word Coverage）</h1>
          <p className="muted">每個單字的目標語言與母語欄位狀態；點單字看每個詞義、例句、衍生詞與相關詞的明細。</p>
        </div>
        <PairPicker />
      </header>
      <div className="toolbar">
        <input className="input" placeholder="搜尋單字" value={q} onChange={(e) => setQ(e.target.value)} aria-label="搜尋單字" />
        <select value={only} onChange={(e) => setOnly(e.target.value)} aria-label="篩選">
          <option value="">全部</option>
          <option value="incomplete">有缺少或失敗</option>
          <option value="failed">有失敗</option>
        </select>
        <div className="seg">
          <button className={view === "words" ? "on" : ""} onClick={() => setView("words")}>依單字</button>
          <button className={view === "fields" ? "on" : ""} onClick={() => setView("fields")}>依欄位</button>
        </div>
      </div>
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
            （重複擷取只計一次，乾跑工作不寫入）
          </p>
          <table className="table">
            <thead>
              <tr><th>單字</th><th>{langName(target)} 欄位</th><th>{langName(native)} 欄位</th><th>缺少</th><th>失敗</th><th>覆寫</th></tr>
            </thead>
            <tbody>
              {cov.data.words.map((w) => (
                <tr key={w.lemma}>
                  <td><Link to={`/words/${target}/${native}/${encodeURIComponent(w.lemma)}`}>{w.lemma}</Link></td>
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
