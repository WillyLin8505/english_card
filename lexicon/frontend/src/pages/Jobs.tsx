import { useState } from "react";
import { api, newIdempotencyKey, type Job } from "../api";
import { Chip, Empty, ErrorBox, Link, Loading, Progress, fmtTime, useApp, useLoad } from "../ui";

export function JobActions({ job, onDone }: { job: Job; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const act = async (action: string) => {
    setBusy(true);
    setErr(null);
    try {
      if (action === "retry-failures") {
        const j = await api.post<Job>(`/imports/${job.id}/retry-failures`, {}, { "Idempotency-Key": newIdempotencyKey() });
        window.location.hash = `/jobs/${j.id}`;
      } else await api.post(`/imports/${job.id}/${action}`);
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const s = job.status;
  return (
    <span className="row-actions">
      {(s === "running" || s === "queued") && <button className="btn btn-small" disabled={busy} onClick={() => act("pause")}>暫停</button>}
      {(s === "paused" || s === "pausing") && <button className="btn btn-small" disabled={busy} onClick={() => act("resume")}>繼續</button>}
      {["queued", "running", "paused", "pausing"].includes(s) && <button className="btn btn-small btn-ghost" disabled={busy} onClick={() => act("cancel")}>取消</button>}
      {["completed_with_errors", "failed", "cancelled", "completed"].includes(s) && job.failed > 0 && (
        <button className="btn btn-small" disabled={busy} onClick={() => act("retry-failures")}>重試失敗項目</button>
      )}
      {err && <span className="bad">{err}</span>}
    </span>
  );
}

export default function Jobs() {
  const { langName } = useApp();
  const jobs = useLoad<Job[]>("/imports", [], 2000);
  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>工作佇列（Jobs）</h1>
          <p className="muted">每 2 秒更新。暫停與取消會在目前單字處理完後生效；續跑從檢查點開始。</p>
        </div>
        <Link to="/imports/new" className="btn btn-primary">開始擷取</Link>
      </header>
      {jobs.error && <ErrorBox error={jobs.error} onRetry={() => jobs.reload()} />}
      {!jobs.data ? (
        <Loading />
      ) : jobs.data.length === 0 ? (
        <Empty>還沒有工作。<Link to="/imports/new">建立第一個乾跑工作</Link>。</Empty>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>#</th><th>單字</th><th>方向</th><th>模式</th><th>狀態</th><th>進度</th><th>成功</th><th>部分</th><th>缺值</th><th>失敗</th><th>建立</th><th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.data.map((j) => (
              <tr key={j.id}>
                <td><Link to={`/jobs/${j.id}`}>#{j.id}</Link>{j.retry_of && <small className="muted"> ↻#{j.retry_of}</small>}</td>
                <td title={j.word_preview.join("、")}>
                  {j.word_preview.map((word, i) => (
                    <span key={word}>
                      {i > 0 && "、"}
                      <Link to={`/words/${j.target_language}/${j.native_language}/${encodeURIComponent(word)}`}>{word}</Link>
                    </span>
                  ))}
                  {j.word_preview_remaining > 0 && <small className="muted">，另 {j.word_preview_remaining} 個</small>}
                  {j.current_word && ["queued", "running", "pausing", "cancelling"].includes(j.status) && (
                    <small className="muted">（目前：{j.current_word}）</small>
                  )}
                </td>
                <td>{langName(j.target_language)}→{langName(j.native_language)}</td>
                <td>{j.mode_label}</td>
                <td><Chip status={j.status} /></td>
                <td className="progress-cell"><Progress value={j.progress} /> {j.checkpoint}/{j.total}</td>
                <td>{j.succeeded}</td>
                <td className={j.partial ? "warn" : ""}>{j.partial}</td>
                <td className={j.missing ? "warn" : ""}>{j.missing}</td>
                <td className={j.failed ? "bad" : ""}>{j.failed}</td>
                <td>{fmtTime(j.created_at)}</td>
                <td><JobActions job={j} onDone={() => jobs.reload(true)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
