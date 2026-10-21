import { useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { api } from "../api";
import { layoutPins } from "../pinLayout";
import { Empty, ErrorBox, Link, Loading, Modal, Progress, fmtDuration, fmtTime, useLoad, useToast } from "../ui";

// 排程看板: the AIs on the left, then two piles side by side an idle AI pulls
// from: one-off cards (the owner's requests and every open 問題回報, by status) and standing
// cards (recurring checks with their live numbers; due ones on top). Drag a
// card onto an AI to hand it over. Below, what runs in the background and
// recent results.

type HistoryEntry = { at: string; by: string; note: string | null; changes: { field: string; from: unknown; to: unknown }[] };
type MetricValue = { value: number | null; label: string; detail?: string };
type Task = {
  id: number; title: string; detail: string | null; status: string; agent: string | null; requested_by: string;
  progress: string | null; issue_ids: number[]; history: HistoryEntry[]; history_n?: number; created_at: string; updated_at: string;
  started_at: string | null; finished_at: string | null; kind: string; interval_minutes: number | null;
  next_run_at: string | null; last_run_at: string | null; last_result: string | null; metric: string | null;
  position: number; stale: boolean; due: boolean; metric_value?: MetricValue;
  difficulty?: number | null; difficulty_reason?: string | null;
};
type IssueCard = { card: "issue"; issue_id: number; title: string; detail: string | null; kind: string; severity: string; area: string; reporter: string; created_at: string;
  difficulty?: number | null; difficulty_reason?: string | null };
type DeckCard = ({ card: "task" } & Task) | IssueCard;
type Bot = { agent: string; kind: string; last_seen: string | null; note: string | null; state: string; doing: Task[]; assigned: Task[]; paused?: boolean; paused_at?: string | null };
type OpenIssue = IssueCard & { linked: { id: number; title: string; status: string; agent: string | null; kind: string }[] };
type Board = { bots: Bot[]; deck: DeckCard[]; recurring: Task[]; done: Task[]; issues?: OpenIssue[] };
type QwenIO = { id?: string; text?: string; out?: string; word?: string; score?: number | null; cefr?: string | null; pos?: string | null; point?: number[] | null; box?: number[] | null };
type PictureDetail = { id: number; words: string[]; tag_status: string; safety_status: string; width: number | null; height: number | null; dropped: number;
  tags: { word: string; point?: number[] | null; box?: number[] | null; score?: number | null; cefr?: string | null; pos?: string | null }[] };
type QwenRequest = { id: number; kind: string; what: string; seconds: number; ref?: string | null; input?: QwenIO[]; output?: QwenIO[] | null };
type Background = {
  jobs: { id: number; mode_label: string; total: number; checkpoint: number; progress: number; current_word: string | null; eta_seconds: number | null }[];
  pictures: { pending: number; done: number; failed: number; labelled_last_hour: number; downloads_waiting: number };
  qwen: { ok: boolean; error?: string; model?: string; parallel?: number; slots?: { total: number | null; busy: number | null; error?: string } | null; requests?: QwenRequest[]; recent?: QwenRequest[] };
  pictures_detail?: Record<string, PictureDetail>;
};
type Meta = { statuses: Record<string, string>; kinds: Record<string, string>; metrics: Record<string, string>; stale_minutes: number; difficulties?: Record<string, string> };
// Card #156/#157: what each AI may take (lexicon/tools/agent_capabilities.json) and its 5-hour / weekly usage.
type Profile = { match?: string[]; max_difficulty: number; prefer_min_difficulty?: number; cost_tier?: string; strengths?: string[]; avoid?: string[]; dispatchable?: boolean };
type UsageWindow = { used_percent: number | null; resets_at: string | null; window_minutes: number | null; exact: boolean; source: string; note: string | null; tokens: number | null };
type AgentUsage = { five_hour?: UsageWindow; weekly?: UsageWindow; observed_at?: string | null; plan?: string | null; limit_message?: string | null; error?: string };
type AgentsInfo = { capabilities: { levels?: Record<string, { label: string; meaning: string }>; agents?: Record<string, Profile>; error?: string };
  usage: { generated_at: string; agents: Record<string, AgentUsage> } };

const STATE: Record<string, [string, string]> = {
  working: ["工作中", "info"], waiting: ["等你回覆", "bad"], blocked: ["卡住", "warn"], stale: ["可能已停止", "warn"],
  idle: ["閒置", "muted"], offline: ["離線", "muted"],
};
const STATUS_TONE: Record<string, string> = { queued: "muted", in_progress: "info", waiting: "bad", blocked: "warn", scheduled: "muted", done: "ok", cancelled: "muted" };
const SEV: Record<string, string> = { high: "高", medium: "中", low: "低" };
// One-off list order (card #459): 進行中 → 等你決定 → 排隊 → 卡住.
type OneOffGroup = "doing" | "waiting" | "queued" | "blocked";
type OneOff = { c: DeckCard | OpenIssue; group: OneOffGroup; pull?: number };
const ONE_OFF_GROUPS: [OneOffGroup, string, string][] = [
  ["doing", "進行中", "info"], ["waiting", "等你決定", "bad"], ["queued", "排隊", "muted"], ["blocked", "卡住", "warn"],
];
const issueGroup = (c: OpenIssue): OneOffGroup => {
  const st = c.linked.map((t) => t.status);
  if (st.includes("in_progress")) return "doing";
  if (c.kind === "decision" || st.includes("waiting")) return "waiting";
  if (st.length === 0 || st.some((s) => s === "queued" || s === "scheduled")) return "queued";
  return "blocked";
};
const ISSUE_KIND: Record<string, string> = { decision: "待你決定", bug: "問題", todo: "未完成需求" };
const QWEN_KIND: Record<string, string> = { translate: "翻譯", tag: "圖片標籤", score: "標籤評分", enrich: "單字補充" };
const FIELD_LABEL: Record<string, string> = { status: "狀態", agent: "負責的 AI", progress: "進度", title: "內容" };
const who = (by: string) => (by === "owner" ? "你" : by);
const every = (min: number | null) => (!min ? "—" : min % 1440 === 0 ? `每 ${min / 1440} 天` : min % 60 === 0 ? `每 ${min / 60} 小時` : `每 ${min} 分鐘`);
const DIFF: Record<number, [string, string]> = { 1: ["簡單", "ok"], 2: ["中等", "info"], 3: ["困難", "warn"], 4: ["極難", "bad"] };
const profileOf = (info: AgentsInfo | null | undefined, name: string): [string, Profile] | null => {
  const agents = info?.capabilities?.agents ?? {};
  if (agents[name]) return [name, agents[name]];
  const hit = Object.entries(agents).find(([, p]) => (p.match ?? []).some((m) => name.startsWith(m)));
  return hit ?? null;
};
const fmtTokens = (n: number | null | undefined) => (n == null ? "—" : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
const initials = (name: string) => (name.startsWith("Codex") ? "Cx" : name.startsWith("Claude") ? "Cl" : name.slice(0, 2));

function Tag({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

// The card's difficulty: a badge, or (editable) a small select that saves it.
function Difficulty({ level, reason, onSet }: { level?: number | null; reason?: string | null; onSet?: (n: number | null) => void }) {
  const [label, tone] = level ? DIFF[level] ?? [String(level), "muted"] : ["未分級", "muted"];
  if (!onSet) return <span className={`chip chip-${tone}`} title={reason ?? undefined}>難度 {label}</span>;
  return (
    <select className={`diff-select chip chip-${tone}`} aria-label="難度" title={reason ?? "設定難度"} value={level ?? ""}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onSet(e.target.value ? Number(e.target.value) : null)}>
      <option value="">難度 未分級</option>
      {[1, 2, 3, 4].map((n) => <option key={n} value={n}>難度 {DIFF[n][0]}</option>)}
    </select>
  );
}

function UsageBar({ label, w }: { label: string; w?: UsageWindow }) {
  if (!w) return <div className="usage-row"><span>{label}</span><span className="muted">未知</span></div>;
  const pct = w.used_percent;
  const tone = pct == null ? "muted" : pct >= 90 ? "bad" : pct >= 60 ? "warn" : "ok";
  return (
    <div className="usage-row" title={`${w.source}${w.note ? ` · ${w.note}` : ""}`}>
      <span>{label}</span>
      <span className="usage-track"><span className={`usage-fill usage-${tone}`} style={{ width: `${Math.min(100, pct ?? 0)}%` }} /></span>
      <span className={pct == null ? "muted" : ""}>{pct == null ? "未知" : `${Math.round(pct)}%${w.exact ? "" : "（估）"}`}</span>
      <small className="muted">
        {w.resets_at ? `重置 ${fmtTime(w.resets_at)}` : ""}
        {pct == null && w.tokens != null ? ` · 已用 ${fmtTokens(w.tokens)} tokens` : ""}
      </small>
    </div>
  );
}

// One row per AI in agent_capabilities.json: what it may take, its cost, and its 5-hour / weekly usage.
function AgentQuota({ info, error }: { info?: AgentsInfo | null; error?: string | null }) {
  if (error || !info) {
    return <p className="muted">{error ? "AI 能力與用量：後端重啟後才會顯示（/schedule/agents-info）。" : "讀取 AI 能力與用量…"}</p>;
  }
  const agents = Object.entries(info.capabilities?.agents ?? {});
  return (
    <section className="card agent-quota" aria-label="AI 能力與用量">
      <h3>能力與用量 <small className="muted">更新 {fmtTime(info.usage?.generated_at)}</small></h3>
      {agents.map(([name, p]) => {
        const u = info.usage?.agents?.[name];
        const max = p.max_difficulty;
        return (
          <div key={name} className="quota-agent">
            <div className="quota-head">
              <strong>{name}</strong>
              {p.dispatchable === false ? <Tag tone="muted">不接看板卡</Tag> : <Tag tone={DIFF[max]?.[1] ?? "muted"}>可接 ≤ {DIFF[max]?.[0] ?? max}</Tag>}
              {p.cost_tier && <small className="muted">成本 {p.cost_tier}</small>}
            </div>
            {p.strengths && p.strengths.length > 0 && <small className="muted">擅長：{p.strengths.join("、")}</small>}
            {u && !u.error && (u.five_hour || u.weekly) && (
              <>
                <UsageBar label="5 小時" w={u.five_hour} />
                <UsageBar label="本週" w={u.weekly} />
                {u.limit_message && <small className="bad">{u.limit_message}</small>}
              </>
            )}
            {u?.error && <small className="bad">用量讀取失敗：{u.error}</small>}
          </div>
        );
      })}
    </section>
  );
}

type Drag = { task_id?: number; issue_id?: number };
const dragKey = "application/x-schedule-card";

export default function Schedule() {
  const { toast, node } = useToast();
  const meta = useLoad<Meta>("/tasks/meta");
  const board = useLoad<Board>("/schedule/board", [], 8000);
  const bg = useLoad<Background>("/schedule/background", [], 5000);
  const info = useLoad<AgentsInfo>("/schedule/agents-info", [], 60000);
  const [editing, setEditing] = useState<Task | "new-once" | "new-recurring" | null>(null);
  const [viewing, setViewing] = useState<Task | null>(null);
  const [dropOn, setDropOn] = useState<string | null>(null);
  const [showIdle, setShowIdle] = useState(false);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast(ok);
      board.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };
  const setDifficulty = (d: Drag, level: number | null) => act(
    () => api.put("/schedule/difficulty", { ...d, difficulty: level, reason: level ? "你在看板上設定" : null, by: "owner" }),
    level ? `難度改為「${DIFF[level][0]}」` : "已清除難度");
  const assign = (agent: string, d: Drag) => act(() => api.post("/schedule/assign", { agent, ...d }), `已交給 ${agent}`);
  const onDrop = (agent: string) => (e: DragEvent) => {
    e.preventDefault();
    setDropOn(null);
    const raw = e.dataTransfer.getData(dragKey);
    if (raw) assign(agent, JSON.parse(raw) as Drag);
  };

  const b = board.data;
  const m = meta.data;
  const bots = b?.bots ?? [];
  const online = bots.filter((x) => x.state !== "offline").length;
  // Only bots with a card in hand (working / waiting / blocked / stale) are shown; idle ones on request.
  const busy = bots.filter((x) => x.doing.length > 0);
  // Paused bots always show (with 暫停中 and a 開始 button), even when idle.
  // Qwen has its own card below; keep it out of the agent list to avoid duplicates.
  const agentsOnly = bots.filter((x) => x.agent !== "Qwen");
  const shown = showIdle ? agentsOnly : agentsOnly.filter((x) => x.doing.length > 0 || x.paused);
  const togglePause = (x: Bot) => act(
    () => api.post(`/agents/${encodeURIComponent(x.agent)}/${x.paused ? "resume" : "pause"}`, {}),
    x.paused ? `${x.agent} 已開始` : `${x.agent} 已暫停（手上的卡做完後不再接新卡）`);
  // Card #459: one list of one-off work — the deck's requests and untaken 問題回報 plus
  // the open reports already on a card or waiting for the owner — grouped by status.
  const oneOff: OneOff[] = [
    ...(b?.deck ?? []).filter((c) => c.card === "issue" || c.kind !== "recurring")
      .map((c, i) => ({ c, group: "queued" as const, pull: i + 1 })),
    ...(b?.issues ?? []).map((c) => ({ c, group: issueGroup(c) })),
  ];
  const oneOffGroups = ONE_OFF_GROUPS.map(([g, label, tone]) => ({ g, label, tone, items: oneOff.filter((x) => x.group === g) }))
    .filter((x) => x.items.length > 0);
  // Due first (oldest due on top), then the ones being worked on, then by next run.
  const rank = (t: Task) => (t.due ? 0 : t.status === "scheduled" ? 2 : 1);
  const standing = [...(b?.recurring ?? [])].sort((x, y) => rank(x) - rank(y)
    || (x.next_run_at ?? "").localeCompare(y.next_run_at ?? "") || x.position - y.position);
  const dueCount = standing.filter((t) => t.due).length;

  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>排程看板（Schedule）</h1>
          <p className="muted">
            左邊是 AI 機器人，右邊兩堆卡：一次性卡（需求、問題回報）和常態卡（定期掃描）。閒置的 AI 會從最上面拉一張來做（<code>task.py next</code>，到期的常態卡優先）。把卡片拖到某個 AI 身上，就是交給它，它下一張會先做這張。
            {m && ` 進行中超過 ${m.stale_minutes} 分鐘沒回報，會標成「可能已停止」。`}
          </p>
        </div>
        <div className="row-actions">
          <button className="btn" onClick={() => setEditing("new-recurring")}>新增常態卡</button>
          <button className="btn btn-primary" onClick={() => setEditing("new-once")}>新增需求</button>
        </div>
      </header>

      {(board.error || meta.error) && <ErrorBox error={(board.error || meta.error)!} onRetry={() => { board.reload(); meta.reload(); }} />}
      {!b || !m ? <Loading /> : (
        <div className="board">
          <aside className="bots" aria-label="AI 機器人">
            <h2>AI 機器人 <small className="muted">{busy.length} 個工作中 · {online} 個在線</small></h2>
            <label className="muted"><input type="checkbox" checked={showIdle} onChange={(e) => setShowIdle(e.target.checked)} /> 顯示閒置／離線的機器人</label>
            <AgentQuota info={info.data} error={info.error} />
            {shown.length === 0 && <Empty>目前沒有機器人在工作。所有工作都要先在看板上有卡（task.py start / next）才能開始。</Empty>}
            {false && <Empty>還沒有 AI 報到。AI 開工時會執行 task.py hello。</Empty>}
            {shown.map((x) => {
              const [label, tone] = STATE[x.state] ?? [x.state, "muted"];
              return (
                <article key={x.agent}
                  className={`card bot bot-${x.state} ${dropOn === x.agent ? "bot-drop" : ""}`}
                  onDragOver={(e) => { if (e.dataTransfer.types.includes(dragKey)) { e.preventDefault(); setDropOn(x.agent); } }}
                  onDragLeave={() => setDropOn(null)}
                  onDrop={onDrop(x.agent)}>
                  <header className="bot-head">
                    <span className={`bot-avatar bot-avatar-${x.agent.startsWith("Codex") ? "codex" : "claude"}`} aria-hidden>{initials(x.agent)}</span>
                    <span className="bot-name">
                      <strong>{x.agent.replace(/^Claude · /, "")}</strong>
                      <small className="muted">{x.agent.startsWith("Claude") ? "Claude" : x.agent.startsWith("Codex") ? "Codex" : x.kind} · {fmtTime(x.last_seen)}</small>
                    </span>
                    {x.paused && <Tag tone="warn">暫停中</Tag>}
                    <Tag tone={tone}>{label}</Tag>
                    <button className={`btn btn-small ${x.paused ? "btn-primary" : ""}`}
                      title={x.paused ? "讓它可以再接新卡" : "暫停：手上的卡可以做完，但不再接新卡"}
                      onClick={() => togglePause(x)}>{x.paused ? "▶ 開始" : "⏸ 暫停"}</button>
                  </header>
                  {(() => {
                    const pr = profileOf(info.data, x.agent);
                    return pr && pr[1].dispatchable !== false ? (
                      <small className="muted">可接難度 ≤ {DIFF[pr[1].max_difficulty]?.[0] ?? pr[1].max_difficulty} · 成本 {pr[1].cost_tier ?? "—"}</small>
                    ) : null;
                  })()}
                  {x.doing.map((t) => <MiniCard key={t.id} t={t} onOpen={() => setViewing(t)} />)}
                  {x.assigned.length > 0 && (
                    <div className="bot-assigned">
                      <small className="muted">待接手 {x.assigned.length} 張</small>
                      {x.assigned.map((t) => <MiniCard key={t.id} t={t} onOpen={() => setViewing(t)} />)}
                    </div>
                  )}
                  {x.doing.length === 0 && x.assigned.length === 0 && <p className="muted bot-empty">沒有卡片 · 拖一張卡過來交給它</p>}
                </article>
              );
            })}
            {(() => {
              const qwenBot = bots.find((x) => x.agent === "Qwen");
              return (
                <QwenBot
                  bg={bg.data}
                  error={bg.error}
                  paused={!!qwenBot?.paused}
                  onToggle={() => togglePause({
                    agent: "Qwen", kind: "model", last_seen: null, note: null,
                    state: qwenBot?.state ?? "idle", doing: [], assigned: [],
                    paused: !!qwenBot?.paused,
                  })}
                />
              );
            })()}
          </aside>

          <main className="deck" aria-label="一次性卡">
            <h2>一次性卡 <small className="muted">{oneOff.length} 張 · 需求與問題回報，做完就結束</small></h2>
            {oneOff.length === 0 ? <Empty>沒有排隊的需求，也沒有未處理的問題回報。</Empty> : oneOffGroups.map(({ g, label, tone, items }) => (
              <section key={g} className="deck-group" aria-label={label}>
                <h3><Tag tone={tone}>{label}</Tag> <small className="muted">{items.length} 張</small></h3>
                <ol className="deck-list">
                  {items.map(({ c, pull }) => {
                    const d: Drag = c.card === "issue" ? { issue_id: c.issue_id } : { task_id: c.id };
                    const key = c.card === "issue" ? `i${c.issue_id}` : `t${c.id}`;
                    const linked = "linked" in c ? c.linked : null;  // an open report already on a card, or a decision
                    return (
                      <li key={key} className={`deck-card deck-${c.card === "issue" ? "issue" : c.kind} ${linked ? "deck-busy" : ""}`} draggable={!linked}
                        onDragStart={(e) => { e.dataTransfer.setData(dragKey, JSON.stringify(d)); e.dataTransfer.effectAllowed = "move"; }}>
                        <div className="deck-top">
                          {pull && <span className="muted mono" title="閒置的 AI 拉卡的順序">{pull}</span>}
                          {c.card === "issue" ? (
                            <>
                              <Tag tone="warn">問題回報 #{c.issue_id}</Tag>
                              <Tag tone={c.kind === "decision" || c.severity === "high" ? "bad" : "muted"}>{ISSUE_KIND[c.kind] ?? c.kind} · {SEV[c.severity] ?? c.severity}</Tag>
                            </>
                          ) : (
                            <Tag tone="muted">需求 #{c.id}</Tag>
                          )}
                          <Difficulty level={c.difficulty} reason={c.difficulty_reason} onSet={(n) => setDifficulty(d, n)} />
                          {!linked && <span className="deck-handle" aria-hidden title="拖到左邊的 AI 上">⠿</span>}
                        </div>
                        <button className="deck-title" onClick={() => c.card === "task" ? setViewing(c) : undefined}>{c.title}</button>
                        {c.detail && <p className="muted deck-detail">{c.detail}</p>}
                        {c.difficulty_reason && <small className="muted diff-reason">{c.difficulty_reason}</small>}
                        <div className="deck-foot">
                          <small className="muted">
                            {c.card === "task" ? `${who(c.requested_by)} 提出 · ${fmtTime(c.created_at)}` : <>
                              {linked && (linked.length > 0
                                ? <>處理中的卡：{linked.map((t) => `#${t.id}（${t.kind === "recurring" ? "常態" : "一次性"}·${m.statuses[t.status] ?? t.status}${t.agent ? `·${t.agent}` : ""}）`).join("、")} · </>
                                : c.kind === "decision" ? "等你在問題回報頁決定 · " : "尚未排入任何卡 · ")}
                              <Link to="/issues">在問題回報查看</Link>
                            </>}
                          </small>
                          {!linked && bots.length > 0 && (
                            <select aria-label="交給哪個 AI" value="" onChange={(e) => e.target.value && assign(e.target.value, d)}>
                              <option value="">交給…</option>
                              {bots.map((x) => <option key={x.agent} value={x.agent}>{x.agent}</option>)}
                            </select>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            ))}
          </main>

          <main className="deck" aria-label="常態卡">
            <h2>常態卡 <small className="muted">{dueCount} 張到期 · 共 {b.recurring.length} 張，定期回到最上面</small></h2>
            {b.recurring.length === 0 ? <Empty>還沒有常態卡。</Empty> : (
              <ol className="deck-list">
                {standing.map((t) => {
                  const free = t.status === "scheduled";
                  return (
                    <li key={t.id} className={`deck-card deck-recurring ${t.due ? "standing-due" : ""} ${free ? "" : "deck-busy"}`} draggable={free}
                      onDragStart={(e) => { e.dataTransfer.setData(dragKey, JSON.stringify({ task_id: t.id })); e.dataTransfer.effectAllowed = "move"; }}>
                      <div className="deck-top">
                        <Tag tone="info">常態卡 #{t.id}</Tag>
                        <Difficulty level={t.difficulty} reason={t.difficulty_reason} onSet={(n) => setDifficulty({ task_id: t.id }, n)} />
                        {t.due ? <Tag tone="bad">到期</Tag> : t.status === "scheduled" ? <Tag tone="muted">等下次執行</Tag>
                          : <Tag tone={STATUS_TONE[t.status] ?? "muted"}>{m.statuses[t.status]}{t.agent ? ` · ${t.agent.replace(/^Claude · /, "")}` : ""}</Tag>}
                        {free && <span className="deck-handle" aria-hidden title="拖到左邊的 AI 上">⠿</span>}
                      </div>
                      <button className="deck-title" onClick={() => setViewing(t)}>{t.title}</button>
                      {t.metric_value && (
                        <div className="standing-metric">
                          <span className="big">{t.metric_value.value ?? "—"}</span>
                          <span>{t.metric_value.label}</span>
                          {t.metric_value.detail && <small className="muted">{t.metric_value.detail}</small>}
                        </div>
                      )}
                      {t.last_result && <p className="standing-last"><small className="muted">上次結果（{fmtTime(t.last_run_at)}）</small><br />{t.last_result}</p>}
                      <div className="deck-foot">
                        <small className="muted">{every(t.interval_minutes)} · 下次 {t.next_run_at && !t.due ? fmtTime(t.next_run_at) : "現在"}</small>
                        {free && !t.due && (
                          <button className="btn btn-small" onClick={() => act(() => api.put(`/tasks/${t.id}`, { next_run_at: new Date().toISOString(), note: "立刻排入" }), `#${t.id} 已排到最上面`)}>立刻排入</button>
                        )}
                        {free && bots.length > 0 && (
                          <select aria-label="交給哪個 AI" value="" onChange={(e) => e.target.value && assign(e.target.value, { task_id: t.id })}>
                            <option value="">交給…</option>
                            {bots.map((x) => <option key={x.agent} value={x.agent}>{x.agent}</option>)}
                          </select>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </main>
        </div>
      )}

      <section>
        <h2>背景程式</h2>
        {bg.data && <BackgroundStrip bg={bg.data} />}
      </section>

      {b && m && b.done.length > 0 && (
        <section>
          <h2>最近完成</h2>
          <ul className="done-list">
            {b.done.map((t) => (
              <li key={t.id}>
                <Tag tone={STATUS_TONE[t.status]}>{m.statuses[t.status]}</Tag>{" "}
                <button className="link-button" onClick={() => setViewing(t)}>#{t.id} {t.title}</button>
                <small className="muted"> · {t.agent ?? "—"} · {fmtTime(t.finished_at)}</small>
                {t.progress && <div className="muted done-result">{t.progress}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {viewing && m && (
        <CardView t={viewing} meta={m} onClose={() => setViewing(null)} onEdit={() => { setEditing(viewing); setViewing(null); }}
          onAct={(fn, ok) => act(async () => { await fn(); setViewing(null); }, ok)} />
      )}
      {editing && m && (
        <TaskForm meta={m} task={typeof editing === "string" ? null : editing}
          recurring={editing === "new-recurring" || (typeof editing !== "string" && editing.kind === "recurring")}
          onClose={() => setEditing(null)}
          onSaved={(msg) => { setEditing(null); toast(msg); board.reload(true); }}
          onDelete={(id) => act(async () => { await api.del(`/tasks/${id}`); setEditing(null); }, `#${id} 已刪除`)} />
      )}
      {node}
    </div>
  );
}

function MiniCard({ t, onOpen }: { t: Task; onOpen: () => void }) {
  return (
    <button className={`mini-card mini-${t.status} ${t.kind === "recurring" ? "mini-recurring" : ""}`} onClick={onOpen}>
      <span className="mini-title"><span className="muted mono">#{t.id}</span> {t.difficulty ? <Difficulty level={t.difficulty} reason={t.difficulty_reason} /> : null} {t.title}</span>
      {t.progress && <span className="muted mini-progress">{t.progress}</span>}
      <span className="mini-meta muted">
        {t.status === "waiting" ? "等你回覆 · " : t.status === "blocked" ? "卡住 · " : t.stale ? "很久沒回報 · " : ""}
        {fmtTime(t.updated_at)}
      </span>
    </button>
  );
}

function QwenBot({ bg, error, paused, onToggle }: {
  bg?: Background | null; error?: string | null; paused?: boolean; onToggle?: () => void;
}) {
  const q = bg?.qwen;
  const reqs = q?.requests ?? [];
  return (
    <article className={`card bot bot-qwen ${paused ? "bot-paused" : ""}`}>
      <header className="bot-head">
        <span className="bot-avatar bot-avatar-qwen" aria-hidden>Qw</span>
        <span className="bot-name">
          <strong>Qwen（{q?.model ?? "本機模型"}）</strong>
          <small className="muted">
            {q?.slots?.total != null ? `${q.slots.total} 個處理位置 · ${q.slots.busy} 個在忙` : "本機 AI 模型 · 自動處理背景工作"}
          </small>
        </span>
        {paused && <Tag tone="warn">暫停中</Tag>}
        {!q ? <Tag tone="muted">讀取中</Tag> : !q.ok ? <Tag tone="bad">無法取得</Tag> : reqs.length ? <Tag tone="info">工作中</Tag> : <Tag tone="muted">閒置</Tag>}
        {onToggle && (
          <button className={`btn btn-small ${paused ? "btn-primary" : ""}`}
            title={paused ? "恢復接受新的推論請求" : "暫停：進行中的請求做完，新請求回 503"}
            onClick={onToggle}>{paused ? "▶ 開始" : "⏸ 暫停"}</button>
        )}
      </header>
      {error && <p className="bad">{error}</p>}
      {q && !q.ok && <p className="bad">{q.error}</p>}
      {reqs.map((r) => (
        <div key={r.id} className={`mini-card mini-qwen ${r.seconds > 300 ? "mini-slow" : ""}`}>
          <span className="mini-title">{QWEN_KIND[r.kind] ?? r.kind}：{r.what || "—"}</span>
          <span className="mini-meta muted">已 {fmtDuration(r.seconds)}</span>
        </div>
      ))}
      {q?.ok && reqs.length === 0 && <p className="muted bot-empty">現在沒有請求。</p>}
    </article>
  );
}

const pictureOf = (r: QwenRequest) => (r.ref?.startsWith("image:") ? Number(r.ref.slice(6)) : null);

type Label = { word: string; point?: number[] | null; score?: number | null; cefr?: string | null; state: "pass" | "fail" | "new" | "checking" | "unscored" };

// Every label known for one picture: the ones it already carries, the new
// ones a finished labelling request produced, and the scores Qwen gave or is
// checking right now.
function labelsFor(id: number, detail: PictureDetail | undefined, now: QwenRequest[], recent: QwenRequest[]): Label[] {
  const out = new Map<string, Label>();
  const put = (w: string, patch: Partial<Label>) => {
    const k = w.toLowerCase();
    out.set(k, { ...(out.get(k) ?? { word: w, state: "unscored" }), ...patch } as Label);
  };
  for (const t of detail?.tags ?? []) put(t.word, { point: t.point, score: t.score, cefr: t.cefr, state: t.score == null ? "unscored" : t.score >= 0.8 ? "pass" : "fail" });
  const mine = (r: QwenRequest) => pictureOf(r) === id;
  for (const r of [...recent].reverse().filter(mine)) {
    for (const o of r.output ?? []) {
      if (!o.word) continue;
      if (r.kind === "tag") put(o.word, { point: o.point ?? out.get(o.word.toLowerCase())?.point, cefr: o.cefr ?? undefined, state: "new" });
      if (r.kind === "score" && o.score != null) put(o.word, { score: o.score, state: o.score >= 0.8 ? "pass" : "fail" });
    }
  }
  for (const r of now.filter(mine)) {
    if (r.kind === "score") for (const i of r.input ?? []) if (i.word) put(i.word, { state: "checking" });
  }
  return [...out.values()];
}

const LABEL_STATE: Record<Label["state"], string> = { pass: "通過 ≥80%", fail: "未通過", new: "剛產生、待評分", checking: "評分中", unscored: "未評分" };

let measureCtx: CanvasRenderingContext2D | null = null;
function textWidth(text: string, font: string) {
  measureCtx ??= document.createElement("canvas").getContext("2d");
  if (!measureCtx) return text.length * 7;
  measureCtx.font = font;
  return measureCtx.measureText(text).width;
}
const LABEL_H = 18;
const labelText = (l: Label) => `${l.word}${l.score != null ? ` ${Math.round(l.score * 100)}` : ""}`;

// The picture with its labels laid out like the app's photo labels
// (pinLayout): no two labels overlap, each joins its spot with a short line.
// Labels that failed (below 80%) are listed under the picture instead, and a
// small picture lists every label underneath rather than crowding it.
function LabelledPicture({ id, detail, labels, big }: { id: number; detail?: PictureDetail; labels: Label[]; big?: boolean }) {
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setSize(el.clientHeight > 20 ? { w: el.clientWidth, h: el.clientHeight } : null));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // A picture can fail while the API restarts: try again a few times.
  const onError = () => {
    setFailed(true);
    if (attempt < 3) setTimeout(() => { setFailed(false); setAttempt((n) => n + 1); }, 10000);
  };
  const onPicture = big ? labels.filter((l) => l.state !== "fail" && l.point && l.point.length >= 2) : [];
  const below = labels.filter((l) => !onPicture.includes(l));
  const key = onPicture.map((l) => `${l.word}:${l.state}:${l.score ?? ""}`).join("|");
  const placed = useMemo(() => {
    if (!size || failed) return [];
    return layoutPins(onPicture.map((l, i) => ({
      id: String(i), anchor: { x: l.point![0] * size.w, y: l.point![1] * size.h },
      w: 12 + textWidth(labelText(l), "600 11px sans-serif"), h: LABEL_H,
    })), size.w, size.h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size, key, failed]);
  return (
    <figure className={`lp ${big ? "lp-big" : ""}`}>
      <div className="lp-stage" ref={ref}>
        {failed ? (
          <div className="lp-missing">圖片 #{id} 無法顯示{detail?.safety_status === "blocked" ? "（安全檢查擋下）" : ""}</div>
        ) : (
          <img src={`/api/schedule/picture/${id}${attempt ? `?try=${attempt}` : ""}`} alt={`圖片 #${id}${detail?.words.length ? `（${detail.words.join("、")}）` : ""}`} onError={onError} />
        )}
        {size && placed.length > 0 && (
          <svg className="lp-leaders" width={size.w} height={size.h} aria-hidden>
            {placed.map((p) => {
              const l = onPicture[Number(p.id)];
              return (
                <g key={p.id} className={`lp-g-${l.state}`}>
                  {p.leader > 1 && <line x1={p.anchor.x} y1={p.anchor.y} x2={p.joint.x} y2={p.joint.y} />}
                  <circle cx={p.anchor.x} cy={p.anchor.y} r={3} />
                </g>
              );
            })}
          </svg>
        )}
        {placed.map((p) => {
          const l = onPicture[Number(p.id)];
          return (
            <span key={p.id} className={`lp-label lp-placed lp-${l.state}`}
              style={{ left: p.badge.l, top: p.badge.t, width: p.badge.r - p.badge.l, height: LABEL_H }}
              title={`${l.word}${l.cefr ? ` · ${l.cefr}` : ""} · ${LABEL_STATE[l.state]}${l.score != null ? ` ${Math.round(l.score * 100)}%` : ""}`}>
              {l.word}{l.score != null && <small> {Math.round(l.score * 100)}</small>}
            </span>
          );
        })}
      </div>
      <figcaption>
        <strong>#{id}</strong> {detail?.words.join("、")}
        <span className="muted"> · {labels.filter((l) => l.state === "pass").length} 個通過 · {labels.filter((l) => l.state === "new" || l.state === "checking").length} 個處理中
          {detail?.safety_status === "unchecked" && " · 尚未安全檢查"}</span>
        {below.length > 0 && (
          <div className="qwen-tags">{below.map((l) => (
            <span key={l.word} className={`pill lp-pill-${l.state}`} title={LABEL_STATE[l.state]}>
              {l.word}{l.score != null && ` ${Math.round(l.score * 100)}%`}
            </span>
          ))}</div>
        )}
      </figcaption>
    </figure>
  );
}

function QwenWork({ r, done }: { r: QwenRequest; done?: boolean }) {
  const pic = pictureOf(r);
  const inputs = r.input ?? [];
  const outputs = r.output ?? [];
  return (
    <article className={`qwen-work qwen-${r.kind}`}>
      <div className="qwen-body">
        <header>
          <Tag tone={done ? "ok" : "info"}>{QWEN_KIND[r.kind] ?? r.kind}</Tag>{" "}
          <strong>{r.what || (pic ? `圖片 #${pic}` : "—")}</strong>
          <small className="muted"> · {done ? (r.seconds < 0.5 ? "取自快取（之前問過）" : `花了 ${fmtDuration(r.seconds)}`) : `已 ${fmtDuration(r.seconds)}`}</small>
        </header>
        {r.kind === "translate" && (
          done && outputs.length ? (
            <ol className="qwen-lines">
              {outputs.slice(0, 6).map((o, k) => (
                <li key={k}><span className="qwen-src">{o.text}</span><span className="qwen-arrow" aria-hidden>→</span><span>{o.out}</span></li>
              ))}
              {outputs.length > 6 && <li className="muted">…還有 {outputs.length - 6} 句</li>}
            </ol>
          ) : inputs.length ? (
            <ol className="qwen-lines">
              {inputs.slice(0, 6).map((i, k) => <li key={k} className="qwen-src">{i.text}</li>)}
              {inputs.length > 6 && <li className="muted">…還有 {inputs.length - 6} 句</li>}
            </ol>
          ) : null
        )}
        {r.kind === "score" && (
          <div className="qwen-tags">
            {(done && outputs.length ? outputs : inputs).map((o, k) => (
              <span key={k} className={`pill ${o.score == null ? "" : o.score >= 0.8 ? "pill-ok" : "pill-bad"}`}>
                {o.word}{o.score != null && ` ${Math.round(o.score * 100)}%`}
              </span>
            ))}
            {!done && <small className="muted">　檢查這些標籤在圖裡看不看得到…</small>}
          </div>
        )}
        {r.kind === "tag" && (
          done ? (
            <div className="qwen-tags">
              {outputs.length === 0 ? <small className="muted">沒有產生新標籤</small> : outputs.map((o, k) => (
                <span key={k} className="pill">{o.word}{o.cefr && <small className="muted"> {o.cefr}</small>}</span>
              ))}
            </div>
          ) : <small className="muted">看圖找出各 CEFR 等級看得到的單字…</small>
        )}
      </div>
    </article>
  );
}

function QwenLive({ q, details }: { q: Background["qwen"]; details: Record<string, PictureDetail> }) {
  if (!q.ok) return <p className="bad">{q.error}</p>;
  const now = q.requests ?? [];
  const recent = q.recent ?? [];
  const uniq = (rs: QwenRequest[]) => [...new Set(rs.map(pictureOf).filter((x): x is number => x != null))];
  const nowPics = uniq(now);
  const recentPics = uniq(recent).filter((id) => !nowPics.includes(id)).slice(0, 4);
  const doing = (id: number) => now.filter((r) => pictureOf(r) === id).map((r) => `${QWEN_KIND[r.kind] ?? r.kind} 已 ${fmtDuration(r.seconds)}`).join("、");
  return (
    <>
      <div className="qwen-live">
        <div>
          <h3>正在標的圖片 <small className="muted">{nowPics.length} 張</small></h3>
          {nowPics.length === 0 ? <p className="muted">現在沒有在標圖片。</p> : nowPics.map((id) => (
            <div key={id} className="qwen-picture">
              <small className="muted">{doing(id)}</small>
              <LabelledPicture id={id} detail={details[id]} labels={labelsFor(id, details[id], now, recent)} big />
            </div>
          ))}
          {recentPics.length > 0 && (
            <>
              <h3>剛標完的圖片</h3>
              <div className="qwen-recent-pics">
                {recentPics.map((id) => <LabelledPicture key={id} id={id} detail={details[id]} labels={labelsFor(id, details[id], now, recent)} />)}
              </div>
            </>
          )}
        </div>
        <div>
          <h3>正在翻譯 <small className="muted">{now.filter((r) => r.kind === "translate").length} 個</small></h3>
          {now.filter((r) => r.kind === "translate").map((r) => <QwenWork key={r.id} r={r} />)}
          <h3>剛翻完</h3>
          {recent.filter((r) => r.kind === "translate").length === 0 ? <p className="muted">還沒有（標籤服務重啟後重新累計）。</p>
            : recent.filter((r) => r.kind === "translate").map((r) => <QwenWork key={r.id} r={r} done />)}
        </div>
      </div>
      <p className="muted lp-legend">
        標籤顏色：<span className="lp-label lp-pass lp-static">通過 ≥80%</span> <span className="lp-label lp-new lp-static">剛產生、待評分</span>{" "}
        <span className="lp-label lp-checking lp-static">評分中</span> <span className="lp-label lp-fail lp-static">未通過</span> <span className="lp-label lp-unscored lp-static">未評分</span>；數字是辨識分數。
      </p>
    </>
  );
}

function BackgroundStrip({ bg }: { bg: Background }) {
  return (
    <div className="bg-grid">
      <article className="card bg-qwen">
        <header className="agent-head">
          <strong>Qwen 實際在做的事</strong>
          <small className="muted">{bg.qwen.slots?.total != null ? `${bg.qwen.slots.busy}/${bg.qwen.slots.total} 個處理位置在忙` : ""}</small>
        </header>
        <QwenLive q={bg.qwen} details={bg.pictures_detail ?? {}} />
      </article>
      <article className="card">
        <header className="agent-head"><strong>擷取工作</strong><Tag tone={bg.jobs.length ? "info" : "muted"}>{bg.jobs.length ? `${bg.jobs.length} 個` : "沒有"}</Tag></header>
        {bg.jobs.length === 0 ? <p className="muted">沒有進行中的擷取。</p> : (
          <ul className="bg-jobs">
            {bg.jobs.map((j) => (
              <li key={j.id}>
                <Link to={`/jobs/${j.id}`}>#{j.id}</Link> {j.mode_label} · {j.checkpoint}/{j.total}
                {j.current_word && <> · 正在處理 <strong>{j.current_word}</strong></>}
                {j.eta_seconds != null && <span className="muted"> · 約剩 {fmtDuration(j.eta_seconds)}</span>}
                <Progress value={j.progress} />
              </li>
            ))}
          </ul>
        )}
      </article>
      <article className="card">
        <header className="agent-head"><strong>圖片</strong></header>
        <dl className="kv-inline">
          <span><dt>等待 AI 標籤</dt><dd>{bg.pictures.pending}</dd></span>
          <span><dt>過去 1 小時標完</dt><dd>{bg.pictures.labelled_last_hour}</dd></span>
          <span><dt>等待下載的字</dt><dd>{bg.pictures.downloads_waiting}</dd></span>
          <span><dt>已標完</dt><dd>{bg.pictures.done}</dd></span>
          <span><dt>標籤失敗</dt><dd>{bg.pictures.failed}</dd></span>
        </dl>
      </article>
    </div>
  );
}

function CardView({ t, meta, onClose, onEdit, onAct }: {
  t: Task; meta: Meta; onClose: () => void; onEdit: () => void; onAct: (fn: () => Promise<unknown>, ok: string) => void;
}) {
  // The board carries only the latest history entries (card #445); load the whole record.
  const [history, setHistory] = useState<HistoryEntry[]>(t.history);
  useEffect(() => {
    let live = true;
    api.get<Task>(`/tasks/${t.id}`).then((full) => { if (live) setHistory(full.history ?? []); }).catch(() => {});
    return () => { live = false; };
  }, [t.id, t.updated_at]);
  return (
    <Modal title={`${t.kind === "recurring" ? "常態卡" : "需求"} #${t.id}`} onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onEdit}>編輯</button>
          {t.status !== "done" && t.status !== "scheduled" && (
            <button className="btn" onClick={() => onAct(() => api.put(`/tasks/${t.id}`, { status: "done" }), `#${t.id} 標為完成`)}>標為完成</button>
          )}
          {(t.status === "in_progress" || t.status === "queued") && t.agent && (
            <button className="btn btn-ghost" onClick={() => onAct(() => api.put(`/tasks/${t.id}`, t.kind === "recurring"
              ? { status: "scheduled", agent: null, note: "放回常態卡" } : { status: "queued", agent: null, note: "放回牌堆" }), `#${t.id} 已放回`)}>放回牌堆</button>
          )}
          {t.status !== "cancelled" && t.kind === "once" && t.status !== "done" && (
            <button className="btn btn-ghost" onClick={() => onAct(() => api.put(`/tasks/${t.id}`, { status: "cancelled" }), `#${t.id} 已取消`)}>取消</button>
          )}
          <button className="btn btn-primary" onClick={onClose}>關閉</button>
        </>
      }>
      <div className="card-view">
        <h3>{t.title}</h3>
        <p>
          <Tag tone={STATUS_TONE[t.status] ?? "muted"}>{meta.statuses[t.status] ?? t.status}</Tag>{" "}
          <span className="pill">{t.agent ?? "還沒有 AI 接手"}</span>{" "}
          {t.kind === "recurring" && <span className="pill">{every(t.interval_minutes)}</span>}{" "}
          <Difficulty level={t.difficulty} reason={t.difficulty_reason}
            onSet={(n) => onAct(() => api.put("/schedule/difficulty", { task_id: t.id, difficulty: n, reason: n ? "你在看板上設定" : null, by: "owner" }), n ? `難度改為「${DIFF[n][0]}」` : "已清除難度")} />
        </p>
        {t.difficulty_reason && <p className="muted">難度理由：{t.difficulty_reason}</p>}
        {t.detail && <div className="issue-text"><h4>說明</h4><p>{t.detail}</p></div>}
        {t.progress && <div className="issue-text"><h4>最新進度</h4><p>{t.progress}</p></div>}
        {t.last_result && <div className="issue-text"><h4>上次結果</h4><p>{t.last_result}</p></div>}
        <dl className="kv-inline issue-refs">
          <span><dt>提出</dt><dd>{who(t.requested_by)} · {fmtTime(t.created_at)}</dd></span>
          {t.started_at && <span><dt>開始</dt><dd>{fmtTime(t.started_at)}</dd></span>}
          {t.finished_at && <span><dt>結束</dt><dd>{fmtTime(t.finished_at)}</dd></span>}
          {t.issue_ids.length > 0 && <span><dt>問題回報</dt><dd>{t.issue_ids.map((n) => <Link key={n} to="/issues">#{n} </Link>)}</dd></span>}
        </dl>
        {history.length > 0 && (
          <details className="issue-history" open>
            <summary>紀錄（{Math.max(history.length, t.history_n ?? 0)}）</summary>
            <ol>
              {history.map((h, k) => (
                <li key={k}>
                  <small className="muted">{fmtTime(h.at)} · {who(h.by)}</small>{" "}
                  {h.changes.map((ch) => (
                    <span key={ch.field} className="pill">
                      {FIELD_LABEL[ch.field] ?? ch.field}：
                      {ch.field === "status" ? `${meta.statuses[String(ch.from)] ?? ch.from ?? "—"} → ${meta.statuses[String(ch.to)] ?? ch.to}` : String(ch.to ?? "—").slice(0, 80)}
                    </span>
                  ))}
                  {h.note && <span>{h.note}</span>}
                </li>
              ))}
            </ol>
          </details>
        )}
      </div>
    </Modal>
  );
}

function TaskForm({ meta, task, recurring, onClose, onSaved, onDelete }: {
  meta: Meta; task: Task | null; recurring: boolean; onClose: () => void; onSaved: (msg: string) => void; onDelete: (id: number) => void;
}) {
  const [f, setF] = useState({
    title: task?.title ?? "", detail: task?.detail ?? "", hours: String((task?.interval_minutes ?? 360) / 60),
    metric: task?.metric ?? "", issue_ids: task?.issue_ids.join(", ") ?? "", note: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    setErr(null);
    const body: Record<string, unknown> = {
      title: f.title, detail: f.detail || null, note: f.note || null, by: "owner",
      issue_ids: f.issue_ids.split(/[\s,，#]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n > 0),
    };
    if (recurring) Object.assign(body, { interval_minutes: Math.max(5, Math.round(Number(f.hours) * 60) || 360), metric: f.metric || null });
    try {
      if (task) {
        await api.put(`/tasks/${task.id}`, body);
        onSaved(`#${task.id} 已儲存`);
      } else {
        const r = await api.post<Task>("/tasks", { ...body, kind: recurring ? "recurring" : "once", requested_by: "owner" });
        onSaved(recurring ? `已新增常態卡 #${r.id}` : `已新增需求 #${r.id}，放在牌堆裡`);
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={task ? `編輯 #${task.id}` : recurring ? "新增常態卡" : "新增需求"} onClose={onClose}
      footer={
        <>
          {err && <span className="bad">{err}</span>}
          {task && <button className="btn btn-ghost" onClick={() => window.confirm(`刪除 #${task.id}「${task.title}」？刪除後無法復原。`) && onDelete(task.id)}>刪除</button>}
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" disabled={busy || !f.title.trim()} onClick={save}>{busy ? "儲存中…" : "儲存"}</button>
        </>
      }>
      <div className="issue-form">
        <label className="field wide"><span>{recurring ? "要定期做什麼" : "需求"}</span>
          <input className="input" value={f.title} onChange={set("title")} autoFocus placeholder={recurring ? "例如：檢查哪些圖片標籤分級錯" : "例如：圖片標籤再快一點"} />
        </label>
        <label className="field wide"><span>說明（AI 拉到這張卡時會看到）</span>
          <textarea rows={4} value={f.detail} onChange={set("detail")} />
        </label>
        <div className="issue-form-row">
          {recurring && (
            <>
              <label className="field"><span>每幾小時一次</span><input className="input" type="number" min={0.1} step={0.5} value={f.hours} onChange={set("hours")} /></label>
              <label className="field"><span>卡片上顯示的數字</span>
                <select value={f.metric} onChange={set("metric")}>
                  <option value="">不顯示</option>
                  {Object.entries(meta.metrics).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
            </>
          )}
          <label className="field"><span>相關問題回報</span><input className="input" value={f.issue_ids} onChange={set("issue_ids")} placeholder="169, 171" /></label>
        </div>
        {task && <label className="field wide"><span>這次修改的說明（寫進紀錄）</span><input className="input" value={f.note} onChange={set("note")} /></label>}
        {!task && !recurring && (
          <p className="muted">新需求會放進右邊牌堆。閒置的 AI 拉卡時會拿到；也可以直接拖給某個 AI。</p>
        )}
      </div>
    </Modal>
  );
}
