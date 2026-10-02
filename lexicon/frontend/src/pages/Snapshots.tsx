import { useState } from "react";
import { api } from "../api";
import { Chip, Empty, ErrorBox, Loading, Modal, fmtBytes, fmtTime, useApp, useLoad, useToast } from "../ui";

type Snap = {
  id: number;
  source: string;
  source_name: string;
  language: string;
  version: string;
  url: string;
  sha256: string | null;
  size_bytes: number | null;
  path: string | null;
  license: string;
  status: string;
  active: boolean;
  row_count: number | null;
  details: Record<string, unknown>;
  error: string | null;
  retrieved_at: string | null;
  created_at: string;
};

const SNAPSHOT_SOURCES: Record<string, string> = {
  tatoeba: "每週 bulk export（目標語言句子、母語句子、句子配對）匯入 PostgreSQL。語言填「目標:母語」，例如 en:zh-TW。",
  cmudict: "下載 cmudict.dict（GitHub master）。",
  oewn: "下載 Open English WordNet 2024（WN-LMF，經 wn 套件）。",
  kaikki: "記錄目前已快取的逐字 JSONL（全量資料包 2–3 GB，未下載）。",
  cefrj: "記錄 CEFR-J／Octanove 詞表檔案與雜湊。",
  wordfreq: "記錄 wordfreq 版本。",
  kaikki_wordlist: "記錄本機字表版本。",
};

export default function Snapshots() {
  const { target, native } = useApp();
  const snaps = useLoad<Snap[]>("/snapshots", [], 3000);
  const [source, setSource] = useState("tatoeba");
  const [language, setLanguage] = useState(`${target}:${native}`);
  const [pick, setPick] = useState<number[]>([]);
  const [cmp, setCmp] = useState<null | { rows_delta: number; bytes_delta: number; same_source: boolean; files: { file: string; a: string | null; b: string | null; changed: boolean }[] }>(null);
  const [verify, setVerify] = useState<null | { ok: boolean | null; files: { file: string; ok: boolean; reason?: string }[] }>(null);
  const [err, setErr] = useState<string | null>(null);
  const { toast, node } = useToast();

  const request = async () => {
    try {
      setErr(null);
      await api.post("/snapshots", { source, language: source === "tatoeba" ? language : language.split(":")[0] });
      toast("已排入佇列，由 Worker 下載與匯入");
      snaps.reload(true);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="page page-wide">
      {node}
      <header className="page-head">
        <div>
          <h1>來源快照（Source Snapshots）</h1>
          <p className="muted">每份快照保存版本、網址、SHA-256、大小、授權與時間；可校驗、比較，或把舊快照設回使用中（回復）。</p>
        </div>
      </header>
      <section className="card form-inline">
        <label className="field">
          <span>來源</span>
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {Object.keys(SNAPSHOT_SOURCES).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>語言</span>
          <input className="input" value={language} onChange={(e) => setLanguage(e.target.value)} />
        </label>
        <button className="btn btn-primary" onClick={request}>下載並匯入</button>
        <p className="hint">{SNAPSHOT_SOURCES[source]}</p>
      </section>
      {err && <ErrorBox error={err} />}
      {snaps.error && <ErrorBox error={snaps.error} onRetry={() => snaps.reload()} />}
      {!snaps.data ? (
        <Loading />
      ) : snaps.data.length === 0 ? (
        <Empty>還沒有快照。沒有 Tatoeba 快照時，例句會暫時走 Tatoeba API。</Empty>
      ) : (
        <>
          <div className="toolbar">
            <span className="muted">勾選兩份快照可比較差異。</span>
            <button className="btn btn-small" disabled={pick.length !== 2} onClick={async () => {
              try { setCmp(await api.get(`/snapshots/compare?a=${pick[0]}&b=${pick[1]}`)); } catch (e) { setErr((e as Error).message); }
            }}>比較</button>
          </div>
          <table className="table">
            <thead><tr><th></th><th>#</th><th>來源</th><th>語言</th><th>版本</th><th>狀態</th><th>筆數</th><th>大小</th><th>SHA-256</th><th>授權</th><th>取得</th><th></th></tr></thead>
            <tbody>
              {snaps.data.map((s) => (
                <tr key={s.id}>
                  <td><input type="checkbox" aria-label={`選擇快照 ${s.id}`} checked={pick.includes(s.id)} onChange={(e) => setPick(e.target.checked ? [...pick, s.id].slice(-2) : pick.filter((x) => x !== s.id))} /></td>
                  <td>{s.id}</td>
                  <td>{s.source_name}</td>
                  <td>{s.language || "—"}</td>
                  <td>{s.version || "—"}</td>
                  <td><Chip status={s.status} />{s.active && <span className="chip chip-ok">使用中</span>}{s.error && <div className="bad msg">{s.error}</div>}</td>
                  <td>{s.row_count?.toLocaleString() ?? "—"}</td>
                  <td>{fmtBytes(s.size_bytes)}</td>
                  <td className="mono" title={s.sha256 ?? ""}>{s.sha256 ? `${s.sha256.slice(0, 12)}…` : "—"}</td>
                  <td>{s.license}</td>
                  <td>{fmtTime(s.retrieved_at)}</td>
                  <td className="row-actions">
                    {s.status === "ready" && (
                      <>
                        <button className="btn btn-small" onClick={async () => { try { setVerify(await api.post(`/snapshots/${s.id}/verify`)); } catch (e) { setErr((e as Error).message); } }}>校驗</button>
                        {!s.active && <button className="btn btn-small" onClick={async () => { try { await api.post(`/snapshots/${s.id}/activate`); toast("已回復為使用中"); snaps.reload(true); } catch (e) { setErr((e as Error).message); } }}>設為使用中</button>}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {cmp && (
        <Modal title="快照比較" onClose={() => setCmp(null)}>
          {!cmp.same_source && <p className="warn">兩份快照的來源或語言不同。</p>}
          <p>筆數差：{cmp.rows_delta >= 0 ? "+" : ""}{cmp.rows_delta.toLocaleString()} · 大小差：{fmtBytes(Math.abs(cmp.bytes_delta))}{cmp.bytes_delta < 0 ? "（減少）" : ""}</p>
          <ul>{cmp.files.map((f) => <li key={f.file}>{f.file}：{f.changed ? <span className="warn">內容不同</span> : "相同"}</li>)}</ul>
        </Modal>
      )}
      {verify && (
        <Modal title="校驗結果" onClose={() => setVerify(null)}>
          <p>{verify.ok === null ? "這份快照沒有記錄檔案雜湊。" : verify.ok ? "所有檔案的 SHA-256 都相符。" : "有檔案不相符或不見了。"}</p>
          <ul>{verify.files.map((f) => <li key={f.file} className={f.ok ? "" : "bad"}>{f.file}：{f.ok ? "相符" : f.reason ?? "雜湊不同"}</li>)}</ul>
        </Modal>
      )}
    </div>
  );
}
