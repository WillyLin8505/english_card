import { useState } from "react";
import { Empty, ErrorBox, Loading, fmtTime, useLoad } from "../ui";

type Stuck = { type: "task" | "issue"; id: number; title: string; stage: string; state: string | null; note: string | null; hours: number };
type Feedback = { id: number; title: string; status: string; stage: string | null; state: string | null; created_at: string; cards: number[] };
type Overview = {
  stages: Record<string, string>;
  tasks: Record<string, number>;
  issues: Record<string, number>;
  start: { task: number; issue: number };
  stuck: Stuck[];
  release: { version: string | null; can_release: boolean; ready: number; reasons: string[] };
  needs_you: string[];
  feedback: Feedback[];
  digest: { date?: string | null; lines?: string[] };
  updated_at: string | null;
};

// The six stages of lexicon/docs/PIPELINE.md, in order; 完成／取消 are the other ways out.
const MAIN = ["dev", "windows_check", "mac_verify", "ipad_verify", "ready", "released"];
const ago = (h: number) => (h >= 48 ? `${Math.floor(h / 24)} 天` : `${h} 小時`);

export default function Flow() {
  const [q, setQ] = useState("");
  const data = useLoad<Overview>(`/flow/overview${q ? `?q=${encodeURIComponent(q)}` : ""}`, [q], 30000);
  if (data.error) return <ErrorBox>{data.error}</ErrorBox>;
  const o = data.data;
  if (!o) return <Loading />;
  const stage = (k: string | null) => (k ? o.stages[k] ?? k : "流程開始前");

  return (
    <>
      <div className="page-head">
        <h1>流程總覽（Pipeline）</h1>
        <p className="muted">
          卡 #{o.start.task}、問題回報 #{o.start.issue} 起自動追蹤
          {o.updated_at ? `，最後更新 ${fmtTime(o.updated_at)}` : ""}
        </p>
      </div>

      <div className="card">
        <h2>需要你</h2>
        {o.needs_you.length === 0 ? <Empty>現在沒有需要你的事</Empty> : <ul>{o.needs_you.map((x) => <li key={x}>{x}</li>)}</ul>}
        {o.digest?.date && <p className="muted">每日摘要 {o.digest.date}：{o.digest.lines?.length ?? 0} 項</p>}
      </div>

      <div className="card">
        <h2>
          這一版能不能發布
          <span className={`chip chip-${o.release.can_release ? "ok" : "bad"}`}>{o.release.can_release ? "可以" : "還不行"}</span>
        </h2>
        <p className="muted">版本 {o.release.version ?? "?"}，{o.release.ready} 張卡已通過 iPad 驗證</p>
        {o.release.reasons.length > 0 && <ul>{o.release.reasons.map((x) => <li key={x}>{x}</li>)}</ul>}
      </div>

      <div className="card">
        <h2>每階段張數</h2>
        <table className="table">
          <thead>
            <tr><th />{MAIN.map((k) => <th key={k}>{o.stages[k]}</th>)}<th>{o.stages.done}</th></tr>
          </thead>
          <tbody>
            <tr><td>卡片</td>{MAIN.map((k) => <td key={k}>{o.tasks[k]}</td>)}<td>{o.tasks.done}</td></tr>
            <tr><td>問題回報</td>{MAIN.map((k) => <td key={k}>{o.issues[k]}</td>)}<td>{o.issues.done}</td></tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>卡住最久</h2>
        {o.stuck.length === 0 ? <Empty>沒有卡住的項目</Empty> : (
          <table className="table">
            <thead><tr><th>項目</th><th>內容</th><th>階段</th><th>已等</th></tr></thead>
            <tbody>
              {o.stuck.map((r) => (
                <tr key={`${r.type}${r.id}`}>
                  <td>{r.type === "task" ? "卡" : "問題"} #{r.id}</td>
                  <td>{r.title}{r.note && <div className="muted">{r.note}</div>}</td>
                  <td>{stage(r.stage)}{r.state === "failed" && <span className="chip chip-bad">不通過</span>}{r.state === "note" && <span className="chip chip-warn">注意</span>}</td>
                  <td>{ago(r.hours)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>手機回饋</h2>
        <input className="input" placeholder="搜尋問題編號或文字" value={q} onChange={(e) => setQ(e.target.value)} />
        {o.feedback.length === 0 ? <Empty>沒有符合的回饋</Empty> : (
          <table className="table">
            <thead><tr><th>問題回報</th><th>內容</th><th>卡號</th><th>階段</th></tr></thead>
            <tbody>
              {o.feedback.map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>{r.title}</td>
                  <td>{r.cards.length ? r.cards.map((c) => `#${c}`).join("、") : "尚未派卡"}</td>
                  <td>{stage(r.stage)}{r.state === "failed" && <span className="chip chip-bad">不通過</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
