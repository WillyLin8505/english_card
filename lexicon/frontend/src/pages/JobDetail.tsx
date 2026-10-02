import { useState } from "react";
import { api, newIdempotencyKey, type JobDetail as JD } from "../api";
import { Chip, Empty, ErrorBox, Link, Loading, Progress, fmtTime, useApp, useLoad } from "../ui";
import { JobActions } from "./Jobs";

export default function JobDetail({ id }: { id: number }) {
  const { langName, fieldLabel, sourceName } = useApp();
  const job = useLoad<JD>(`/imports/${id}`, [id], 2000);
  const [tab, setTab] = useState<"steps" | "errors" | "logs">("steps");
  const [dlErr, setDlErr] = useState<string | null>(null);
  if (job.error) return <div className="page"><ErrorBox error={job.error} onRetry={() => job.reload()} /></div>;
  if (!job.data) return <Loading />;
  const j = job.data;
  const active = ["queued", "running", "pausing", "cancelling"].includes(j.status);
  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <p><Link to="/jobs">← 工作佇列</Link></p>
          <h1>
            工作 #{j.id} <Chip status={j.status} />
          </h1>
          <p className="muted">
            {langName(j.target_language)} → {langName(j.native_language)} · {j.mode_label} · {j.total} 個單字 · {j.fields} 個欄位
            {j.retry_of && <> · 重試自 <Link to={`/jobs/${j.retry_of}`}>#{j.retry_of}</Link></>}
            {j.note && <> · {j.note}</>}
          </p>
        </div>
        <JobActions job={j} onDone={() => job.reload(true)} />
      </header>
      <section className="card">
        <div className="progress-big">
          <Progress value={j.progress} tone={j.failed ? "warn" : undefined} />
          <strong>{Math.round(j.progress * 100)}%</strong>
        </div>
        <dl className="kv kv-inline">
          <dt>檢查點</dt><dd>{j.checkpoint} / {j.total}</dd>
          <dt>目前單字</dt><dd>{active && j.current_word ? j.current_word : "—"}</dd>
          <dt>欄位成功</dt><dd>{j.succeeded}</dd>
          <dt>部分</dt><dd className="warn">{j.partial}</dd>
          <dt>缺值</dt><dd className="warn">{j.missing}</dd>
          <dt>失敗</dt><dd className="bad">{j.failed}</dd>
          <dt>未設定</dt><dd>{j.unset}</dd>
          <dt>跳過（已完成）</dt><dd>{j.skipped}</dd>
          <dt>Worker</dt><dd>{j.worker_id ?? "—"}</dd>
          <dt>心跳</dt><dd>{fmtTime(j.heartbeat_at)}</dd>
          <dt>開始</dt><dd>{fmtTime(j.started_at)}</dd>
          <dt>結束</dt><dd>{fmtTime(j.finished_at)}</dd>
        </dl>
        {j.status === "queued" && <p className="warn">排隊中：請確認 Worker 已啟動（python worker/worker.py）。</p>}
      </section>
      {!active && j.mode === "dry_run" && <RunForReal job={j} />}
      {!active && j.mode !== "dry_run" && j.mode !== "validate_only" && j.words.length > 0 && (
        <section className="card">
          <p>
            已寫入詞庫：
            {j.words.slice(0, 20).map((w, i) => (
              <span key={w}>
                {i > 0 && "、"}
                <Link to={`/words/${j.target_language}/${j.native_language}/${encodeURIComponent(w)}`}>{w}</Link>
              </span>
            ))}
            {j.words.length > 20 && <span className="muted">，另 {j.words.length - 20} 個</span>}
          </p>
        </section>
      )}
      <div className="seg" role="tablist">
        {([
          ["steps", `欄位與來源步驟（${j.steps.length}）`],
          ["errors", `錯誤（${j.errors.length}）`],
          ["logs", "即時紀錄"],
        ] as const).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {l}
          </button>
        ))}
      </div>
      {tab === "steps" &&
        (j.steps.length === 0 ? (
          <Empty>還沒有處理任何欄位。</Empty>
        ) : (
          <table className="table">
            <thead><tr><th>欄位</th><th>來源</th><th>順位</th><th>成功</th><th>無資料</th><th>失敗</th><th>未查詢</th><th>重試</th><th>平均</th></tr></thead>
            <tbody>
              {j.steps.map((s) => (
                <tr key={`${s.field}-${s.source}`}>
                  <td>{s.label}</td><td>{sourceName(s.source)}</td><td>{s.position || "—"}</td>
                  <td>{s.succeeded}</td><td>{s.missing}</td><td className={s.failed ? "bad" : ""}>{s.failed}</td>
                  <td className="muted">{s.skipped}</td><td>{s.retried}</td><td>{s.avg_ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
      {tab === "errors" && (
        <>
          <div className="toolbar">
            <div className="chips-row">
              {j.errors_by_type.map((e) => (
                <span key={`${e.error_type}-${e.source}`} className="pill">
                  {e.error_type} · {sourceName(e.source)}：{e.count}
                </span>
              ))}
            </div>
            <button
              className="btn btn-small"
              onClick={async () => {
                try {
                  setDlErr(null);
                  await api.download(`/imports/${j.id}/errors.csv`, `job-${j.id}-errors.csv`);
                } catch (e) {
                  setDlErr((e as Error).message);
                }
              }}
            >
              下載錯誤 CSV
            </button>
          </div>
          {dlErr && <ErrorBox error={dlErr} />}
          {j.errors.length === 0 ? (
            <Empty>沒有錯誤。</Empty>
          ) : (
            <table className="table">
              <thead><tr><th>單字</th><th>欄位</th><th>來源</th><th>類型</th><th>訊息</th><th>嘗試</th><th>下次重試</th></tr></thead>
              <tbody>
                {j.errors.map((e) => (
                  <tr key={e.id}>
                    <td><Link to={`/words/${j.target_language}/${j.native_language}/${encodeURIComponent(e.lemma)}`}>{e.lemma}</Link></td>
                    <td>{e.field === "*" ? "整個單字" : fieldLabel(e.field)}</td>
                    <td>{e.source === "*" ? "—" : sourceName(e.source)}</td>
                    <td><span className="chip chip-bad">{e.error_type}</span></td>
                    <td className="msg">{e.message}</td>
                    <td>{e.attempts}</td>
                    <td>{fmtTime(e.next_retry_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {tab === "logs" && (
        <ul className="logs" aria-live="polite">
          {j.logs.map((l) => (
            <li key={l.id} className={`log-${l.level}`}>
              <time>{fmtTime(l.at)}</time> {l.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A finished 乾跑 wrote nothing: say so, and fetch the same words for real. */
function RunForReal({ job }: { job: JD }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [idem] = useState(newIdempotencyKey);
  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const next = await api.post<JD>("/imports", {
        target_language: job.target_language,
        native_language: job.native_language,
        mode: "fill_missing",
        words: job.words,
        fields: job.field_list,
        sources: job.sources,
        note: `正式擷取（乾跑 #${job.id} 的單字）`,
      }, { "Idempotency-Key": idem });
      window.location.hash = `/jobs/${next.id}`;
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <section className="card">
      <p className="warn">這是乾跑：只預覽查詢結果，沒有寫入詞庫。</p>
      <button className="btn btn-primary" disabled={busy} onClick={start}>
        {busy ? "建立中…" : `正式擷取這 ${job.words.length} 個單字`}
      </button>
      {err && <ErrorBox error={err} />}
    </section>
  );
}
