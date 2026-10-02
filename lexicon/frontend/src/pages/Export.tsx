import { useState } from "react";
import { api, newIdempotencyKey } from "../api";
import { Chip, Empty, ErrorBox, Loading, PairPicker, Rate, fmtBytes, fmtTime, useApp, useLoad } from "../ui";

type Release = {
  id: number;
  target_language: string;
  native_language: string;
  status: string;
  file_name: string | null;
  sha256: string | null;
  size_bytes: number | null;
  include_audio: boolean;
  checks: { check: string; ok: boolean; message: string; level: string }[];
  error: string | null;
  created_at: string;
  files: { name: string; bytes: number }[];
  counts: Record<string, number> | null;
  completeness: Record<string, { complete: number; total: number; rate: number }> | null;
};

export default function Export() {
  const { target, native, langName, fieldLabel } = useApp();
  const list = useLoad<Release[]>("/exports", []);
  const [audio, setAudio] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [last, setLast] = useState<Release | null>(null);

  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.post<Release>("/exports/sqlite", { target_language: target, native_language: native, include_audio: audio }, { "Idempotency-Key": newIdempotencyKey() });
      setLast(r);
      list.reload(true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const download = async (r: Release, name: string) => {
    try {
      await api.download(`/exports/${r.id}/files/${encodeURIComponent(name)}`, name);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>匯出給 Flutter（Export for Flutter）</h1>
          <p className="muted">每個語言方向各自一份：language-data-{"{目標}-{母語}-{時間}"}.sqlite、音檔清單與 manifest.json。匯出前檢查外鍵、孤立音檔、必要欄位、翻譯配對與可讀性；失敗不會留下看似完成的檔案。</p>
        </div>
      </header>
      <section className="card form-inline">
        <PairPicker />
        <label className="check">
          <input type="checkbox" checked={audio} onChange={(e) => setAudio(e.target.checked)} /> 包含音檔（複製到 media/audio/{target}/）
        </label>
        <button className="btn btn-primary" disabled={busy} onClick={run}>
          {busy ? "建立中…" : `建立 ${langName(target)}→${langName(native)} 資料包`}
        </button>
      </section>
      {err && <ErrorBox error={err} />}
      {last && <ReleaseCard r={last} onDownload={download} fieldLabel={fieldLabel} />}
      <h2>歷次匯出</h2>
      {list.error && <ErrorBox error={list.error} onRetry={() => list.reload()} />}
      {!list.data ? (
        <Loading />
      ) : list.data.length === 0 ? (
        <Empty>還沒有匯出過。</Empty>
      ) : (
        list.data.filter((r) => r.id !== last?.id).map((r) => <ReleaseCard key={r.id} r={r} onDownload={download} fieldLabel={fieldLabel} compact />)
      )}
    </div>
  );
}

function ReleaseCard({ r, onDownload, fieldLabel, compact }: { r: Release; onDownload: (r: Release, name: string) => void; fieldLabel: (k: string) => string; compact?: boolean }) {
  const { langName } = useApp();
  return (
    <div className="card release">
      <h3>
        #{r.id} {langName(r.target_language)}→{langName(r.native_language)} <Chip status={r.status} /> <small className="muted">{fmtTime(r.created_at)}</small>
      </h3>
      {r.error && <ErrorBox error={r.error} />}
      {r.file_name && <p className="mono">{r.file_name} · SHA-256 {r.sha256?.slice(0, 16)}… · {fmtBytes(r.size_bytes)}</p>}
      {r.files.length > 0 && (
        <div className="chips-row">
          {r.files.map((f) => (
            <button key={f.name} className="btn btn-small" onClick={() => onDownload(r, f.name)}>
              下載 {f.name}（{fmtBytes(f.bytes)}）
            </button>
          ))}
        </div>
      )}
      {r.checks.length > 0 && (
        <ul className="checks">
          {r.checks.map((c) => (
            <li key={c.check} className={c.level === "error" ? "bad" : c.level === "warning" ? "warn" : "ok"}>
              {c.level === "error" ? "✗" : c.level === "warning" ? "!" : "✓"} {c.message}
            </li>
          ))}
        </ul>
      )}
      {!compact && r.counts && (
        <dl className="kv kv-inline">
          {Object.entries(r.counts).map(([k, v]) => (
            <span key={k}><dt>{k}</dt><dd>{v}</dd></span>
          ))}
        </dl>
      )}
      {!compact && r.completeness && (
        <details>
          <summary>各欄位完整率</summary>
          <table className="table compact">
            <tbody>
              {Object.entries(r.completeness).map(([k, v]) => (
                <tr key={k}><td>{fieldLabel(k)}</td><td><Rate value={v.rate} /></td><td>{v.complete}/{v.total}</td></tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}
