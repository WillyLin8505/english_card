import { Fragment } from "react";
import { Chip, Empty, ErrorBox, Link, Loading, Rate, fmtBytes, fmtTime, useApp, useLoad } from "../ui";

type Dash = {
  pairs: {
    target_language: string;
    native_language: string;
    words: number;
    target_rate: number | null;
    native_rate: number | null;
    example_pairing_rate: number | null;
    derived_meaning_rate: number | null;
    missing: number;
    failed: number;
  }[];
  running_jobs: { id: number; status: string; target_language: string; native_language: string; checkpoint: number; total: number }[];
  source_health: { source: string; name: string; ok: number; missing: number; failed: number; error_rate: number; last: string; breaker_open: boolean }[];
  api_usage: { source: string; day: string; requests: number; errors: number; cache_hits: number; avg_ms: number }[];
  storage: { database_bytes: number; audio_bytes: number; image_bytes: number };
  images: { eligible_senses: number; approved_senses: number; pending: number; coverage: number | null };
  counts: Record<string, number>;
};

export default function Dashboard() {
  const { langName } = useApp();
  const d = useLoad<Dash>("/dashboard", [], 5000);
  if (d.error) return <div className="page"><ErrorBox error={d.error} onRetry={() => d.reload()} /></div>;
  if (!d.data) return <Loading />;
  const x = d.data;
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>總覽</h1>
          <p className="muted">每個語言方向的完整率、執行中工作、來源健康度與容量。</p>
        </div>
        <div className="actions">
          <Link to="/imports/new" className="btn btn-primary">開始擷取</Link>
          <Link to="/policies" className="btn">設定來源順位</Link>
        </div>
      </header>

      <section>
        <h2>語言方向</h2>
        {x.pairs.length === 0 ? (
          <Empty>
            還沒有任何詞條。先到 <Link to="/policies">來源順位</Link> 測試單字，再 <Link to="/imports/new">開始擷取</Link>（建議先乾跑）。
          </Empty>
        ) : (
          <div className="cards">
            {x.pairs.map((p) => (
              <div key={`${p.target_language}-${p.native_language}`} className="card">
                <h3>
                  {langName(p.target_language)} → {langName(p.native_language)}
                </h3>
                <p className="big">{p.words} <small>個詞條</small></p>
                <dl className="kv">
                  <dt>目標語言欄位</dt><dd><Rate value={p.target_rate} /></dd>
                  <dt>母語翻譯</dt><dd><Rate value={p.native_rate} /></dd>
                  <dt>例句配對</dt><dd><Rate value={p.example_pairing_rate} /></dd>
                  <dt>衍生詞詞義</dt><dd><Rate value={p.derived_meaning_rate} /></dd>
                  <dt>缺少／失敗</dt><dd><span className="warn">{p.missing}</span> ／ <span className="bad">{p.failed}</span></dd>
                </dl>
                <Link to="/coverage">查看覆蓋率 →</Link>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid2">
        <section>
          <h2>執行中的工作</h2>
          {x.running_jobs.length === 0 ? (
            <Empty>沒有執行中或排隊的工作。</Empty>
          ) : (
            <ul className="list">
              {x.running_jobs.map((j) => (
                <li key={j.id}>
                  <Link to={`/jobs/${j.id}`}>#{j.id}</Link> {langName(j.target_language)}→{langName(j.native_language)} <Chip status={j.status} /> {j.checkpoint}/{j.total}
                </li>
              ))}
            </ul>
          )}
          <h2>容量</h2>
          <dl className="kv">
            <dt>PostgreSQL</dt><dd>{fmtBytes(x.storage.database_bytes)}</dd>
            <dt>音檔</dt><dd>{fmtBytes(x.storage.audio_bytes)}</dd>
            <dt>圖片</dt><dd>{fmtBytes(x.storage.image_bytes)}</dd>
            <dt>已核准圖片覆蓋率</dt><dd>{x.images.coverage == null ? "—" : `${Math.round(x.images.coverage * 100)}%`}（{x.images.approved_senses}／{x.images.eligible_senses} 個名詞詞義；待審核 {x.images.pending} 張）</dd>
            {Object.entries(x.counts).map(([k, v]) => (
              <Fragment key={k}>
                <dt>{({ lexemes: "詞條", senses: "詞義", examples: "例句", audio: "音檔", candidates: "候選值" } as Record<string, string>)[k] ?? k}</dt>
                <dd>{v.toLocaleString()}</dd>
              </Fragment>
            ))}
          </dl>
        </section>
        <section>
          <h2>來源健康度（24 小時）</h2>
          {x.source_health.length === 0 ? (
            <Empty>24 小時內沒有查詢紀錄。</Empty>
          ) : (
            <table className="table">
              <thead><tr><th>來源</th><th>成功</th><th>無資料</th><th>失敗</th><th>錯誤率</th><th>最後查詢</th></tr></thead>
              <tbody>
                {x.source_health.map((h) => (
                  <tr key={h.source}>
                    <td>{h.name}{h.breaker_open && <span className="chip chip-bad">熔斷中</span>}</td>
                    <td>{h.ok}</td><td>{h.missing}</td><td className={h.failed ? "bad" : ""}>{h.failed}</td>
                    <td>{Math.round(h.error_rate * 100)}%</td><td>{fmtTime(h.last)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h2>API 使用量</h2>
          {x.api_usage.length === 0 ? (
            <Empty>還沒有網路請求紀錄。</Empty>
          ) : (
            <table className="table">
              <thead><tr><th>日期</th><th>來源</th><th>請求</th><th>快取命中</th><th>錯誤</th><th>平均</th></tr></thead>
              <tbody>
                {x.api_usage.map((u) => (
                  <tr key={`${u.day}-${u.source}`}>
                    <td>{u.day}</td><td>{u.source}</td><td>{u.requests}</td><td>{u.cache_hits}</td>
                    <td className={u.errors ? "bad" : ""}>{u.errors}</td><td>{u.avg_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </div>
  );
}
