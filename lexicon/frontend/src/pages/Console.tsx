import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Loading, Modal, fmtTime, useLoad, useToast } from "../ui";
import { Decide, IssueForm, Screenshot, type Issue, type IssueMeta } from "./Issues";
import ConsoleAi, { RUN_STATE } from "./ConsoleAi";
import { TaskForm, Tag, type Meta as TaskMeta } from "./Schedule";

// 控制台 (card #919): 排程, 流程總覽 and 問題回報 as one entry with three tabs. The tabs share the data, the
// filters and the open item, so moving between them loses nothing. A card and its 問題回報 are one item.

export type Need = { key: string | null; kind: string; title: string; ask: string; options: string[]; since: string | null };
export type Run = { card: number; title: string; agent: string | null; state: string; pid: number | null; started_at: string | null; last_activity: string | null; also?: number[] };
export type Session = { name: string; status: string | null; started_at: string | null; last_activity: string | null };
export type Runs = { working: Run[]; collecting: Run[]; waiting: Run[]; idle: Run[]; session: Run[]; sessions: Session[];
  lingering: { card: number; agent: string | null; started_at: string | null }[]; counts: Record<string, number> };
type Stuck = { key: string; title: string; stage_label: string; wait_label: string; state: string | null; hours: number };
type Overview = {
  needs_you: Need[];
  release: { version: string | null; can_release: boolean; ready: number; reasons: string[] };
  counts: Record<string, number>;
  stages: Record<string, string>;
  main_stages: string[];
  stuck: Stuck[];
  runs: Runs;
  cards_verifying: number;
  legacy_waiting: number;
  digest: { date?: string | null; lines?: string[]; mailed?: string | null; mail_error?: string | null };
  gmail_ready?: boolean | null;
  flow_at: string | null;
  groups: Record<string, number>;
};
type Row = {
  key: string; title: string; type: string; type_label: string; source: string; source_label: string; stage: string; stage_label: string;
  state: string | null; wait: string; wait_label: string; status_text: string; group: string; severity: string | null;
  cards: number[]; issues: number[]; agent: string | null; since: string | null; created_at: string;
};
type ItemMeta = { sources: Record<string, string>; types: Record<string, string>; stages: Record<string, string>; waits: Record<string, string>; group_labels: Record<string, string> };
type Items = { items: Row[]; total: number; groups: Record<string, number>; meta: ItemMeta };
type Step = { key: string; label: string; state: string; at: string | null; by: string | null; evidence: string[] };
type Instruction = { at: string | null; text: string; kind: string; where: string };
type Detail = Row & {
  need: (Need & { issue?: number; task?: number }) | null;
  timeline: Step[];
  main_card: number | null;
  actions: string[];
  run: { state: string; last_activity: string | null; started_at: string | null } | null;
  cards_full: { id: number; title: string; detail: string | null; status: string; status_label: string; agent: string | null; progress: string | null }[];
  issues_full: Issue[];
  instructions: Instruction[];
  log: { at: string | null; by: string | null; what: string; note: string | null; changes: { field: string; to: unknown }[] }[];
};
type Filters = { group: string; source: string; type: string; stage: string; wait: string; q: string };

const POLL_MS = 30000;
const TABS: [string, string, string][] = [["/console", "現況", "now"], ["/console/items", "全部項目", "items"], ["/console/ai", "AI 與常態檢查", "ai"]];
const NO_FILTER: Filters = { group: "active", source: "", type: "", stage: "", wait: "", q: "" };
const OLD_ROUTES: Record<string, string> = { "/flow": "/console", "/issues": "/console/items", "/schedule": "/console/ai" };
const WAIT_TONE: Record<string, string> = { you: "bad", ai: "info", stuck: "warn", paused: "warn", mac: "info", system: "muted", queue: "muted", release: "ok", none: "ok" };
const ACTION: Record<string, string> = { pause: "⏸ 暫停", resume: "▶ 繼續", top: "提到最前", bottom: "排到最後", redo: "退回重做", cancel: "取消這項" };
const STEP_MARK: Record<string, string> = { done: "✓", current: "●", failed: "✕", skipped: "－", todo: "○" };
const FIELD: Record<string, string> = { status: "狀態", agent: "負責的 AI", progress: "進度", title: "內容", stage: "階段", instruction: "補充指示", decision: "決定", resolution: "處理方式", severity: "嚴重度", kind: "類型" };
const ago = (h: number) => (h >= 48 ? `${Math.floor(h / 24)} 天` : `${h} 小時`);
const who = (x: string | null) => (x === "owner" ? "你" : x ?? "");

export const consoleRedirect = (route: string) => OLD_ROUTES[route.split("?")[0]] ?? null;

function openFrom(route: string) {
  return new URLSearchParams(route.split("?")[1] ?? "").get("open");
}

function Conn({ error, updatedAt, flowAt }: { error: string | null; updatedAt: Date | null; flowAt?: string | null }) {
  const clock = updatedAt?.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  if (error?.startsWith("Not Found") || error?.startsWith("404")) {
    return <p className="console-conn bad" role="status">後端 API 還是舊版，重新啟動後才有控制台資料；「AI 與常態檢查」分頁仍可用。</p>;
  }
  return (
    <p className={`console-conn ${error ? "bad" : "muted"}`} role="status">
      {error ? `後端暫時連不上，畫面停在 ${clock ?? "上一次"} 的資料，會自動重試，不用重新整理。` : `每 30 秒自動更新，最後更新 ${clock ?? "—"}`}
      {!error && flowAt ? `；流程資料 ${fmtTime(flowAt)}` : ""}
    </p>
  );
}

export default function Console({ route }: { route: string }) {
  const { toast, node } = useToast();
  const path = route.split("?")[0];
  const tab = TABS.find(([p]) => p === path) ?? TABS[0];
  const overview = useLoad<Overview>("/console/overview", [], POLL_MS);
  const [filters, setFilters] = useState<Filters>(NO_FILTER);
  const [open, setOpen] = useState<string | null>(openFrom(route));
  const [adding, setAdding] = useState<"need" | "report" | null>(null);
  const issueMeta = useLoad<IssueMeta>("/issues/meta");
  const taskMeta = useLoad<TaskMeta>("/tasks/meta");

  useEffect(() => {
    const key = openFrom(route);
    if (key) setOpen(key);
  }, [route]);

  const refresh = () => overview.reload(true);
  const showFiltered = (f: Partial<Filters>) => {
    setFilters({ ...NO_FILTER, group: "all", ...f });
    window.location.hash = "/console/items";
  };
  const act = useCallback(async (key: string, action: string, text?: string, agent?: string) => {
    try {
      const r = await api.post<{ message: string }>(`/console/items/${key}/act`, { action, text, agent });
      toast(r.message);
      overview.reload(true);
      return true;
    } catch (e) {
      toast((e as Error).message, "bad");
      return false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const o = overview.data;
  return (
    <div className="page page-wide console">
      <header className="page-head">
        <div>
          <h1>控制台</h1>
          <Conn error={overview.error} updatedAt={overview.updatedAt} flowAt={o?.flow_at} />
        </div>
        <div className="row-actions">
          <button className="btn" onClick={() => setAdding("report")}>新增回報</button>
          <button className="btn btn-primary" onClick={() => setAdding("need")}>新增需求</button>
        </div>
      </header>
      <nav className="seg console-tabs" role="tablist" aria-label="控制台分頁">
        {TABS.map(([p, label]) => (
          <a key={p} role="tab" aria-selected={tab[0] === p} className={tab[0] === p ? "on" : ""} href={`#${p}`}>
            {label}
            {p === "/console" && (o?.needs_you.length ?? 0) > 0 && <span className="chip chip-bad">{o!.needs_you.length}</span>}
          </a>
        ))}
      </nav>

      {tab[2] === "now" && (o ? <Now o={o} onOpen={setOpen} onFilter={showFiltered} act={act} />
        : overview.error ? <ErrorBox error={overview.error} onRetry={refresh} /> : <Loading />)}
      {tab[2] === "items" && <AllItems filters={filters} setFilters={setFilters} onOpen={setOpen} />}
      {tab[2] === "ai" && <ConsoleAi runs={o?.runs} onOpen={setOpen} toast={toast} />}

      {open && <ItemPanel itemKey={open} onClose={() => setOpen(null)} act={act} />}
      {adding === "need" && taskMeta.data && (
        <TaskForm meta={taskMeta.data} task={null} recurring={false} onClose={() => setAdding(null)}
          onSaved={(msg) => { setAdding(null); toast(msg); refresh(); }} onDelete={() => undefined} />
      )}
      {adding === "report" && issueMeta.data && (
        <IssueForm meta={issueMeta.data} issue={null} onClose={() => setAdding(null)}
          onSaved={(msg) => { setAdding(null); toast(msg); refresh(); }} onDelete={() => undefined} />
      )}
      {node}
    </div>
  );
}

// ── 現況 ──────────────────────────────────────────────────────────

function Now({ o, onOpen, onFilter, act }: {
  o: Overview; onOpen: (k: string) => void; onFilter: (f: Partial<Filters>) => void;
  act: (key: string, action: string, text?: string) => Promise<boolean>;
}) {
  const r = o.runs;
  return (
    <>
      <section className="card console-needs" aria-label="需要你">
        <h2>需要你 {o.needs_you.length > 0 && <span className="chip chip-bad">{o.needs_you.length}</span>}</h2>
        {o.needs_you.length === 0 ? <p className="console-calm">目前不需要你</p> : (
          <ul className="need-list">{o.needs_you.map((n) => <NeedRow key={`${n.key}${n.kind}`} n={n} onOpen={onOpen} act={act} />)}</ul>
        )}
      </section>

      <section className="card">
        <h2>這一版能不能發布 <Tag tone={o.release.can_release ? "ok" : "bad"}>{o.release.can_release ? "可以" : "還不行"}</Tag></h2>
        <p className="muted">版本 {o.release.version ?? "?"}，{o.release.ready} 張卡已通過 iPad 驗證</p>
        {o.release.reasons.length > 0 && <ul>{o.release.reasons.map((x) => <li key={x}>{x}</li>)}</ul>}
      </section>

      <section className="card">
        <h2>每階段張數 <small className="muted">點一下看清單</small></h2>
        <div className="stage-strip">
          {o.main_stages.map((k) => (
            <button key={k} className="stage-cell" onClick={() => onFilter({ stage: k })}>
              <span className="big">{o.counts[k] ?? 0}</span><small>{o.stages[k]}</small>
            </button>
          ))}
        </div>
        <p className="muted">
          做完但還沒過驗證的卡 {o.cards_verifying} 張
          {o.legacy_waiting > 0 && `（含流程開始前的舊卡 ${o.legacy_waiting} 張）`}。這些不算完成。
        </p>
      </section>

      <section className="card">
        <h2>卡住最久</h2>
        {o.stuck.length === 0 ? <Empty>沒有卡住的項目</Empty> : (
          <ul className="item-list">
            {o.stuck.map((x) => (
              <li key={x.key}>
                <button className="item-row" onClick={() => onOpen(x.key)}>
                  <span className="item-title">{x.title}</span>
                  <span className="item-meta muted">
                    {x.stage_label} · {x.wait_label} · 已等 {ago(x.hours)}
                    {x.state === "failed" && <Tag tone="bad">不通過</Tag>}{x.state === "note" && <Tag tone="warn">注意</Tag>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>真的在跑的 AI</h2>
        <p className="run-counts">
          <Tag tone="info">工作中 {r.counts.working}</Tag>
          <Tag tone="muted">等收卡 {r.counts.collecting}</Tag>
          <Tag tone={r.counts.waiting ? "bad" : "muted"}>等你 {r.counts.waiting}</Tag>
          <Tag tone="muted">閒置／舊卡 {r.counts.idle}</Tag>
        </p>
        {r.working.length === 0 ? <Empty>現在沒有 CLI 在跑</Empty> : (
          <ul className="item-list">
            {r.working.map((x) => (
              <li key={x.card}>
                <button className="item-row" onClick={() => onOpen(`t${x.card}`)}>
                  <span className="item-title">#{x.card} {x.title}</span>
                  <span className="item-meta muted">{x.agent} · 開始 {fmtTime(x.started_at)} · 最後活動 {fmtTime(x.last_activity)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {o.digest?.date && (
          <p className="muted">
            每日摘要 {o.digest.date}：{o.digest.lines?.length ?? 0} 項
            {o.digest.mailed === o.digest.date ? "，已寄 Gmail" : o.digest.mail_error ? `，${o.digest.mail_error}` : ""}
          </p>
        )}
      </section>
    </>
  );
}

function NeedRow({ n, onOpen, act }: { n: Need; onOpen: (k: string) => void; act: (key: string, action: string, text?: string) => Promise<boolean> }) {
  const [text, setText] = useState("");
  const key = n.key;
  return (
    <li className="need">
      <div>
        <strong>{n.ask}</strong>
        {n.ask.indexOf(n.title.slice(0, 20)) < 0 && <div className="muted">{n.title}</div>}
      </div>
      {key && (
        <div className="need-answer">
          {n.options.map((x) => <button key={x} className="btn btn-small" onClick={() => act(key, "answer", x)}>{x}</button>)}
          <input className="input" placeholder={n.kind === "decision" ? "其他：寫下你要的…" : "寫回覆…"} value={text} aria-label="回覆"
            onChange={(e) => setText(e.target.value)} />
          <button className="btn btn-primary btn-small" disabled={!text.trim()} onClick={async () => { if (await act(key, "answer", text.trim())) setText(""); }}>送出</button>
          <button className="btn btn-small btn-ghost" onClick={() => onOpen(key)}>查看</button>
        </div>
      )}
    </li>
  );
}

// ── 全部項目 ──────────────────────────────────────────────────────

function AllItems({ filters, setFilters, onOpen }: { filters: Filters; setFilters: (f: Filters) => void; onOpen: (k: string) => void }) {
  const [limit, setLimit] = useState(200);
  const query = new URLSearchParams(Object.entries({ ...filters, limit: String(limit) }).filter(([, v]) => v)).toString();
  const list = useLoad<Items>(`/console/items?${query}`, [], POLL_MS);
  const m = list.data?.meta;
  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setFilters({ ...filters, [k]: e.target.value });
  const pick = (k: keyof Filters, label: string, opts?: Record<string, string>) => (
    <select value={filters[k]} onChange={set(k)} aria-label={label}>
      <option value="">{label}：全部</option>
      {Object.entries(opts ?? {}).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
    </select>
  );
  return (
    <>
      <div className="toolbar">
        <div className="seg" role="tablist" aria-label="分類">
          {Object.entries(m?.group_labels ?? { active: "要處理", qc: "長期 QC", closed: "已結案", all: "全部" }).map(([k, label]) => (
            <button key={k} role="tab" aria-selected={filters.group === k} className={filters.group === k ? "on" : ""}
              onClick={() => setFilters({ ...filters, group: k })}>
              {label} <small className="muted">{list.data?.groups[k] ?? ""}</small>
            </button>
          ))}
        </div>
        <div className="form-inline console-filters">
          {pick("source", "來源", m?.sources)}
          {pick("type", "類型", m?.types)}
          {pick("stage", "階段", m?.stages)}
          {pick("wait", "等誰", m?.waits)}
          <input className="input" type="search" placeholder="搜尋編號或文字" value={filters.q} onChange={set("q")} aria-label="搜尋" />
        </div>
      </div>
      {list.error && !list.data && <ErrorBox error={list.error} onRetry={() => list.reload()} />}
      {!list.data ? !list.error && <Loading /> : list.data.items.length === 0 ? <Empty>這個篩選下沒有項目。</Empty> : (
        <>
          <p className="muted">共 {list.data.total} 項</p>
          <ul className="item-list">
            {list.data.items.map((r) => (
              <li key={r.key}>
                <button className={`item-row wait-${r.wait}`} onClick={() => onOpen(r.key)}>
                  <span className="item-title">
                    {r.severity === "high" && <Tag tone="bad">高</Tag>}
                    {r.title}
                  </span>
                  <span className="item-meta muted">
                    <Tag tone={WAIT_TONE[r.wait] ?? "muted"}>{r.status_text}</Tag>
                    {r.state === "failed" && <Tag tone="bad">不通過</Tag>}
                    {r.state === "note" && <Tag tone="warn">注意</Tag>}
                    <span>{r.stage_label}</span> · <span>{r.source_label}</span> · <span>{r.type_label}</span>
                    {r.cards.length > 0 && <span> · 卡 {r.cards.slice(-2).map((c) => `#${c}`).join("、")}</span>}
                    {r.issues.length > 0 && <span> · 問題 {r.issues.slice(0, 2).map((c) => `#${c}`).join("、")}</span>}
                    <span> · {fmtTime(r.since)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {list.data.total > list.data.items.length && (
            <button className="btn" onClick={() => setLimit(limit + 200)}>再顯示 200 項</button>
          )}
        </>
      )}
    </>
  );
}

// ── 一個項目：時間軸與介入 ────────────────────────────────────────

function Timeline({ steps }: { steps: Step[] }) {
  return (
    <ol className="timeline" aria-label="時間軸">
      {steps.map((x) => (
        <li key={x.key} className={`tl tl-${x.state}`}>
          <span className="tl-mark" aria-hidden>{STEP_MARK[x.state]}</span>
          <div>
            <strong>{x.label}</strong>
            {x.state === "current" && <Tag tone="info">現在在這裡</Tag>}
            {x.state === "failed" && <Tag tone="bad">不通過</Tag>}
            {(x.at || x.by) && <small className="muted"> {x.at ? fmtTime(x.at) : ""}{x.by ? ` · ${who(x.by)}` : ""}</small>}
            {x.evidence.map((e, k) => <div key={k} className="muted tl-note">{e}</div>)}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <div className="issue-text"><h4>{title}</h4>{children}</div>;
}

function ItemPanel({ itemKey, onClose, act }: {
  itemKey: string; onClose: () => void; act: (key: string, action: string, text?: string, agent?: string) => Promise<boolean>;
}) {
  const item = useLoad<Detail>(`/console/items/${itemKey}`, [], POLL_MS);
  const [text, setText] = useState("");
  const d = item.data;
  const run = async (action: string, body?: string, agent?: string) => {
    if (await act(itemKey, action, body, agent)) item.reload(true);
    return true;
  };
  const risky = (action: string) => {
    const running = d?.run?.state === "running";
    const say = action === "cancel" ? `取消「${d?.title}」？${running ? "正在跑的 CLI 會被結束。" : ""}`
      : action === "pause" && running ? "暫停會結束正在跑的 CLI，已做的修改留在工作目錄。繼續？"
      : action === "redo" ? `退回重做「${d?.title}」？${running ? "正在跑的 CLI 會被結束。" : ""}` : null;
    if (say && !window.confirm(say)) return;
    run(action, action === "redo" ? text.trim() || undefined : undefined).then(() => action === "redo" && setText(""));
  };
  return (
    <Modal title={d ? d.title.slice(0, 60) : "項目"} onClose={onClose}
      footer={<button className="btn btn-primary" onClick={onClose}>關閉</button>}>
      {item.error && !d && <ErrorBox error={item.error} onRetry={() => item.reload()} />}
      {!d ? !item.error && <Loading /> : (
        <div className="card-view">
          <p>
            <Tag tone={WAIT_TONE[d.wait] ?? "muted"}>{d.status_text}</Tag>
            <span className="pill">{d.stage_label}</span> <span className="pill">{d.source_label}</span> <span className="pill">{d.type_label}</span>
            {d.agent && <span className="pill">{d.agent}</span>}
            {d.run && <Tag tone="muted">{RUN_STATE[d.run.state] ?? d.run.state}</Tag>}
            {d.run?.last_activity && <small className="muted"> 最後活動 {fmtTime(d.run.last_activity)}</small>}
          </p>
          {d.need && (
            <div className="issue-decide">
              <h4>{d.need.ask}</h4>
              {d.need.kind === "decision" && d.issues_full[0]
                ? <Decide issue={d.issues_full.find((i) => i.id === d.need!.issue) ?? d.issues_full[0]} onDecide={(x) => run("answer", x)} />
                : (d.need.options ?? []).map((x) => <button key={x} className="btn btn-small" onClick={() => run("answer", x)}>{x}</button>)}
            </div>
          )}
          <Section title="時間軸"><Timeline steps={d.timeline} /></Section>
          <Section title="介入">
            <div className="row-actions console-actions">
              {d.actions.filter((a) => ACTION[a]).map((a) => (
                <button key={a} className={`btn btn-small ${a === "cancel" ? "btn-ghost" : ""}`} onClick={() => risky(a)}>{ACTION[a]}</button>
              ))}
            </div>
            <textarea rows={2} className="input console-instruct" value={text} onChange={(e) => setText(e.target.value)}
              placeholder={d.need ? "回覆或補充指示…" : "補充指示：AI 接下來要注意什麼…"} aria-label="補充指示" />
            <div className="row-actions">
              <button className="btn btn-small btn-primary" disabled={!text.trim()}
                onClick={() => run("instruct", text.trim()).then(() => setText(""))}>送出補充指示</button>
              {d.need && d.need.kind !== "decision" && (
                <button className="btn btn-small" disabled={!text.trim()} onClick={() => run("answer", text.trim()).then(() => setText(""))}>當作回覆送出</button>
              )}
            </div>
            {d.instructions.length > 0 && (
              <ul className="delivered">
                {d.instructions.map((x, k) => (
                  <li key={k}><small className="muted">{fmtTime(x.at)}</small> {x.text}<div className="muted">→ {x.where}</div></li>
                ))}
              </ul>
            )}
          </Section>
          {d.cards_full.map((c) => (
            <details key={c.id} className="issue-history">
              <summary>卡 #{c.id}：{c.status_label}{c.agent ? ` · ${c.agent}` : ""}</summary>
              {c.progress && <p>{c.progress}</p>}
              {c.detail && <p className="console-detail">{c.detail}</p>}
            </details>
          ))}
          {d.issues_full.map((i) => (
            <details key={i.id} className="issue-history" open={d.cards_full.length === 0}>
              <summary>問題回報 #{i.id}：{i.title}</summary>
              {i.detail && <p className="console-detail">{i.detail}</p>}
              {i.has_screenshot && <Screenshot id={i.id} />}
              {i.steps && <p><strong>重現步驟：</strong>{i.steps}</p>}
              {i.expected && <p><strong>預期：</strong>{i.expected}</p>}
              {i.actual && <p><strong>實際：</strong>{i.actual}</p>}
              {i.decision && <p><strong>你的決定：</strong>{i.decision}</p>}
              {i.resolution && <p><strong>處理方式：</strong>{i.resolution}</p>}
            </details>
          ))}
          {d.log.length > 0 && (
            <details className="issue-history">
              <summary>紀錄（{d.log.length}）</summary>
              <ol>
                {d.log.map((h, k) => (
                  <li key={k}>
                    <small className="muted">{fmtTime(h.at)} · {who(h.by)} · {h.what}</small>{" "}
                    {h.changes.map((c) => <span key={c.field} className="pill">{FIELD[c.field] ?? c.field}：{String(c.to ?? "—").slice(0, 60)}</span>)}
                    {h.note && <span> {h.note}</span>}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </Modal>
  );
}
