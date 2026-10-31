import { useState } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading, fmtTime, useLoad } from "../ui";
import type { Run, Runs } from "./Console";
import { AgentQuota, BackgroundStrip, CardView, Difficulty, QwenBot, STATUS_TONE, Tag, TaskForm, every,
  type AgentsInfo, type Background, type Board, type Meta, type Task } from "./Schedule";

// 控制台「AI 與常態檢查」: what each CLI really does (the same numbers as 現況), then the capacity, pause
// buttons and standing cards, folded away because they rarely need a look.

export const RUN_STATE: Record<string, string> = {
  running: "工作中", collecting: "等收卡", waiting: "等你", idle: "閒置／舊卡", blocked: "卡住", paused: "已暫停", session: "互動 session",
};
const BOT_STATE: Record<string, [string, string]> = {
  working: ["工作中", "info"], collecting: ["等收卡", "muted"], waiting: ["等你", "bad"], blocked: ["卡住", "warn"],
  stale: ["閒置／舊卡", "muted"], idle: ["閒置", "muted"], offline: ["離線", "muted"],
};
const GROUPS: [keyof Runs, string, string][] = [
  ["working", "工作中", "程序確實活著、屬於這張卡"], ["collecting", "等收卡", "結果已寫好，派工程式下一輪收"],
  ["waiting", "等你", "在「現況」回覆"], ["idle", "閒置／舊卡", "卡還開著，但沒有程序在跑"],
];

function RunTable({ rows, onOpen }: { rows: Run[]; onOpen: (k: string) => void }) {
  return (
    <div className="table-scroll">
      <table className="table">
        <thead><tr><th>卡</th><th>內容</th><th>AI</th><th>開始</th><th>最後活動</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.card}>
              <td><button className="link-button" onClick={() => onOpen(`t${r.card}`)}>#{r.card}</button></td>
              <td>{r.title}{r.state !== "running" && r.state !== "collecting" && r.state !== "waiting" && <small className="muted"> · {RUN_STATE[r.state]}</small>}</td>
              <td>
                {r.agent ?? "—"}
                {(r.also?.length ?? 0) > 0 && <Tag tone="warn">同名還掛 {r.also!.map((c) => `#${c}`).join("、")}</Tag>}
              </td>
              <td>{fmtTime(r.started_at)}</td>
              <td>{fmtTime(r.last_activity)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ConsoleAi({ runs, onOpen, toast }: { runs?: Runs; onOpen: (k: string) => void; toast: (t: string, tone?: string) => void }) {
  const board = useLoad<Board>("/schedule/board", [], 30000);
  const meta = useLoad<Meta>("/tasks/meta");
  const bg = useLoad<Background>("/schedule/background", [], 15000);
  const info = useLoad<AgentsInfo>("/schedule/agents-info", [], 60000);
  const [showIdle, setShowIdle] = useState(false);
  const [viewing, setViewing] = useState<Task | null>(null);
  const [editing, setEditing] = useState<Task | "new" | null>(null);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast(ok);
      board.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };
  const bots = (board.data?.bots ?? []).filter((b) => b.agent !== "Qwen");
  const qwen = board.data?.bots.find((b) => b.agent === "Qwen");
  const shownBots = showIdle ? bots : bots.filter((b) => b.doing.length > 0 || b.paused);
  const toggle = (name: string, paused: boolean) => act(() => api.post(`/agents/${encodeURIComponent(name)}/${paused ? "resume" : "pause"}`, {}),
    paused ? `${name} 已開始` : `${name} 已暫停（手上的卡做完後不再接新卡）`);
  const standing = [...(board.data?.recurring ?? [])].sort((a, b) => Number(b.due) - Number(a.due) || (a.next_run_at ?? "").localeCompare(b.next_run_at ?? ""));
  const m = meta.data;

  return (
    <>
      <section className="card" aria-label="CLI 現況">
        <h2>CLI 現況</h2>
        {!runs ? <p className="muted">等控制台資料…</p> : GROUPS.map(([k, label, hint]) => {
          const rows = runs[k] as Run[];
          return (
            <div key={k} className="run-group">
              <h3>{label} <span className="chip chip-muted">{rows.length}</span> <small className="muted">{hint}</small></h3>
              {rows.length > 0 && <RunTable rows={rows} onOpen={onOpen} />}
            </div>
          );
        })}
        {(runs?.lingering.length ?? 0) > 0 && (
          <p className="muted">卡已收但程序還沒結束：{runs!.lingering.map((x) => `#${x.card}（${x.agent ?? "?"}）`).join("、")}</p>
        )}
      </section>

      {runs && (
        <section className="card" aria-label="互動的 Claude session">
          <h2>互動的 Claude session <small className="muted">有人在操作，不算派工數字</small></h2>
          {runs.session.length > 0 && <RunTable rows={runs.session} onOpen={onOpen} />}
          {runs.sessions.length === 0 ? <Empty>現在沒有互動的 session</Empty> : (
            <ul className="item-list">
              {runs.sessions.map((x, k) => (
                <li key={k} className="item-static">
                  <span className="item-title">{x.name}</span>
                  <span className="item-meta muted">{x.status === "busy" ? "忙碌" : "閒置"} · 開始 {fmtTime(x.started_at)} · 最後活動 {fmtTime(x.last_activity)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <details className="card console-fold">
        <summary><h2>AI 額度</h2></summary>
        <AgentQuota info={info.data} error={info.error} />
      </details>

      <details className="card console-fold">
        <summary><h2>機器人與暫停 <small className="muted">{bots.filter((b) => b.paused).length} 個暫停中</small></h2></summary>
        <label className="muted"><input type="checkbox" checked={showIdle} onChange={(e) => setShowIdle(e.target.checked)} /> 顯示閒置／離線的機器人（{bots.length}）</label>
        {board.error && !board.data && <ErrorBox error={board.error} onRetry={() => board.reload()} />}
        {!board.data ? !board.error && <Loading /> : (
          <ul className="item-list">
            {shownBots.map((b) => {
              const [label, tone] = BOT_STATE[b.state] ?? [b.state, "muted"];
              return (
                <li key={b.agent} className="item-static">
                  <span className="item-title">{b.agent.replace(/^Claude · /, "")}</span>
                  <span className="item-meta muted">
                    {b.doing.length > 0 && `卡 ${b.doing.map((t) => `#${t.id}`).join("、")} · `}{fmtTime(b.last_seen)}
                    {b.paused && <Tag tone="warn">暫停中</Tag>}
                    <Tag tone={tone}>{label}</Tag>
                    <button className={`btn btn-small ${b.paused ? "btn-primary" : ""}`} onClick={() => toggle(b.agent, !!b.paused)}>{b.paused ? "▶ 開始" : "⏸ 暫停"}</button>
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        <QwenBot bg={bg.data} error={bg.error} paused={!!qwen?.paused} onToggle={() => toggle("Qwen", !!qwen?.paused)} />
      </details>

      <details className="card console-fold" open>
        <summary><h2>常態檢查 <small className="muted">{standing.filter((t) => t.due).length} 張到期 · 共 {standing.length} 張</small></h2></summary>
        <div className="row-actions"><button className="btn btn-small" onClick={() => setEditing("new")}>新增常態卡</button></div>
        {standing.length === 0 ? <Empty>還沒有常態卡。</Empty> : (
          <ul className="item-list">
            {standing.map((t) => (
              <li key={t.id} className="item-static standing-row">
                <button className="link-button item-title" onClick={() => setViewing(t)}>#{t.id} {t.title}</button>
                <span className="item-meta muted">
                  {t.due ? <Tag tone="bad">到期</Tag> : t.status === "scheduled" ? <Tag tone="muted">等下次執行</Tag>
                    : <Tag tone={STATUS_TONE[t.status] ?? "muted"}>{m?.statuses[t.status] ?? t.status}</Tag>}
                  {t.metric_value && <span>{t.metric_value.value ?? "—"} {t.metric_value.label} · </span>}
                  {every(t.interval_minutes)} · 下次 {t.next_run_at && !t.due ? fmtTime(t.next_run_at) : "現在"}
                  <Difficulty level={t.difficulty} reason={t.difficulty_reason} />
                  {t.status === "scheduled" && !t.due && (
                    <button className="btn btn-small" onClick={() => act(() => api.put(`/tasks/${t.id}`, { next_run_at: new Date().toISOString(), note: "立刻排入" }), `#${t.id} 已排到最上面`)}>立刻排入</button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </details>

      <details className="card console-fold">
        <summary><h2>背景程式</h2></summary>
        {bg.data && <BackgroundStrip bg={bg.data} />}
      </details>

      {viewing && m && (
        <CardView t={viewing} meta={m} onClose={() => setViewing(null)} onEdit={() => { setEditing(viewing); setViewing(null); }}
          onAct={(fn, ok) => act(async () => { await fn(); setViewing(null); }, ok)} />
      )}
      {editing && m && (
        <TaskForm meta={m} task={editing === "new" ? null : editing} recurring onClose={() => setEditing(null)}
          onSaved={(msg) => { setEditing(null); toast(msg); board.reload(true); }}
          onDelete={(id) => act(async () => { await api.del(`/tasks/${id}`); setEditing(null); }, `#${id} 已刪除`)} />
      )}
    </>
  );
}
