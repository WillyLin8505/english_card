import { useMemo, useState, type ReactNode } from "react";
import { api } from "../api";
import { Empty, ErrorBox, Link, Loading, Modal, fmtTime, useLoad, useToast } from "../ui";

// 問題回報: problems found while using or testing the app, admin and card
// studio; requirements not built yet; and questions waiting for your decision.

type HistoryEntry = { at: string; by: string; note: string | null; changes: { field: string; from: unknown; to: unknown }[] };
export type Issue = {
  id: number;
  kind: string;
  status: string;
  severity: string;
  area: string;
  title: string;
  detail: string | null;
  steps: string | null;
  expected: string | null;
  actual: string | null;
  resolution: string | null;
  options: string[] | null;
  decision: string | null;
  target_language: string | null;
  native_language: string | null;
  lemma: string | null;
  code_ref: string | null;
  spec_ref: string | null;
  reporter: string;
  history: HistoryEntry[];
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
};
type IssueMeta = { kinds: Record<string, string>; statuses: Record<string, string>; severities: Record<string, string>; areas: Record<string, string> };

const STATUS_TONE: Record<string, string> = { open: "warn", in_progress: "info", needs_decision: "bad", fixed: "ok", wont_fix: "muted" };
const KIND_TONE: Record<string, string> = { bug: "bad", todo: "info", decision: "warn" };
const SEV_TONE: Record<string, string> = { high: "bad", medium: "warn", low: "muted" };
const FIELD_LABEL: Record<string, string> = { status: "狀態", decision: "決定", resolution: "處理方式", severity: "嚴重度", kind: "類型" };
const REPORTER: Record<string, string> = { manual: "手動", "claude-simulation": "模擬使用者", "claude-review": "規格比對", owner: "你" };

const TABS: [string, string][] = [
  ["active", "未結案"],
  ["needs_decision", "等你決定"],
  ["bug", "問題"],
  ["todo", "未完成需求"],
  ["closed", "已結案"],
  ["all", "全部"],
];

function tabQuery(tab: string) {
  if (tab === "active" || tab === "closed" || tab === "needs_decision") return `status=${tab}`;
  if (tab === "bug" || tab === "todo") return `kind=${tab}&status=active`;
  return "";
}

const EMPTY_FORM = {
  kind: "bug", status: "open", severity: "medium", area: "app", title: "", detail: "", steps: "", expected: "", actual: "",
  resolution: "", options: "", target_language: "", native_language: "", lemma: "", code_ref: "", spec_ref: "", note: "",
};
type Form = typeof EMPTY_FORM;

function toForm(i: Issue): Form {
  return {
    kind: i.kind, status: i.status, severity: i.severity, area: i.area, title: i.title, detail: i.detail ?? "", steps: i.steps ?? "",
    expected: i.expected ?? "", actual: i.actual ?? "", resolution: i.resolution ?? "", options: (i.options ?? []).join("\n"),
    target_language: i.target_language ?? "", native_language: i.native_language ?? "", lemma: i.lemma ?? "",
    code_ref: i.code_ref ?? "", spec_ref: i.spec_ref ?? "", note: "",
  };
}

function fromForm(f: Form) {
  const opt = f.options.split("\n").map((s) => s.trim()).filter(Boolean);
  return {
    ...f,
    options: opt.length ? opt : null,
    target_language: f.target_language || null,
    native_language: f.native_language || null,
    lemma: f.lemma || null,
    note: f.note || null,
  };
}

function Tag({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`chip chip-${tone}`}>{children}</span>;
}

function Text({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="issue-text">
      <h4>{label}</h4>
      <p>{value}</p>
    </div>
  );
}

export default function Issues() {
  const [tab, setTab] = useState("active");
  const [area, setArea] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [editing, setEditing] = useState<Issue | "new" | null>(null);
  const { toast, node } = useToast();
  const meta = useLoad<IssueMeta>("/issues/meta");
  const query = [tabQuery(tab), area && `area=${area}`, q.trim() && `q=${encodeURIComponent(q.trim())}`].filter(Boolean).join("&");
  const list = useLoad<{ items: Issue[]; counts: Record<string, number> }>(`/issues${query ? `?${query}` : ""}`, [], 15000);

  const counts = useMemo(() => {
    const c = list.data?.counts ?? {};
    const sum = (pred: (kind: string, status: string) => boolean) =>
      Object.entries(c).reduce((n, [k, v]) => (pred(...(k.split(":") as [string, string])) ? n + v : n), 0);
    const closed = (s: string) => s === "fixed" || s === "wont_fix";
    return {
      active: sum((_, s) => !closed(s)),
      needs_decision: sum((_, s) => s === "needs_decision"),
      bug: sum((k, s) => k === "bug" && !closed(s)),
      todo: sum((k, s) => k === "todo" && !closed(s)),
      closed: sum((_, s) => closed(s)),
      all: sum(() => true),
      fixed: sum((_, s) => s === "fixed"),
    } as Record<string, number>;
  }, [list.data]);

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn();
      toast(ok);
      list.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    }
  };

  const m = meta.data;
  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>問題回報（Issue Reports）</h1>
          <p className="muted">
            使用或模擬使用時發現的問題、還沒做的需求，以及需要你決定的事項。每次改狀態、決定或處理方式都會留下紀錄。
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setEditing("new")}>新增回報</button>
      </header>

      <div className="cards issue-stats">
        <div className="card"><h3>等你決定</h3><div className={`big ${counts.needs_decision ? "bad" : ""}`}>{counts.needs_decision}</div></div>
        <div className="card"><h3>待處理問題</h3><div className="big">{counts.bug}</div></div>
        <div className="card"><h3>未完成需求</h3><div className="big">{counts.todo}</div></div>
        <div className="card"><h3>已修正</h3><div className="big ok">{counts.fixed}</div></div>
      </div>

      <div className="toolbar">
        <div className="seg" role="tablist" aria-label="篩選">
          {TABS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
              {label} <small className="muted">{counts[k] ?? 0}</small>
            </button>
          ))}
        </div>
        <div className="form-inline">
          <select value={area} onChange={(e) => setArea(e.target.value)} aria-label="範圍">
            <option value="">全部範圍</option>
            {m && Object.entries(m.areas).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input className="input" type="search" placeholder="搜尋標題、內容、單字" value={q} onChange={(e) => setQ(e.target.value)} aria-label="搜尋" />
        </div>
      </div>

      {(list.error || meta.error) && <ErrorBox error={(list.error || meta.error)!} onRetry={() => { list.reload(); meta.reload(); }} />}
      {!list.data || !m ? (
        <Loading />
      ) : list.data.items.length === 0 ? (
        <Empty>{tab === "needs_decision" ? "目前沒有需要你決定的事。" : "這個篩選下沒有回報。"}</Empty>
      ) : (
        <div className="issue-list">
          {list.data.items.map((i) => {
            const expanded = open[i.id] ?? i.status === "needs_decision";
            return (
              <article key={i.id} className={`card issue issue-${i.status}`}>
                <header className="issue-head" onClick={() => setOpen({ ...open, [i.id]: !expanded })}>
                  <span className="caret" aria-hidden>{expanded ? "▾" : "▸"}</span>
                  <span className="muted mono">#{i.id}</span>
                  <Tag tone={KIND_TONE[i.kind] ?? "muted"}>{m.kinds[i.kind] ?? i.kind}</Tag>
                  <Tag tone={SEV_TONE[i.severity] ?? "muted"}>{m.severities[i.severity] ?? i.severity}</Tag>
                  <button className="issue-title" aria-expanded={expanded}>{i.title}</button>
                  <span className="issue-meta">
                    <span className="pill">{m.areas[i.area] ?? i.area}</span>
                    {i.lemma && <span className="pill">{i.lemma}</span>}
                    <Tag tone={STATUS_TONE[i.status] ?? "muted"}>{m.statuses[i.status] ?? i.status}</Tag>
                    <small className="muted">{fmtTime(i.updated_at)}</small>
                  </span>
                </header>
                {expanded && (
                  <div className="issue-body">
                    <Text label="說明" value={i.detail} />
                    <Text label="重現步驟" value={i.steps} />
                    <div className="grid2">
                      <Text label="預期" value={i.expected} />
                      <Text label="實際" value={i.actual} />
                    </div>
                    {i.status === "needs_decision" && (
                      <Decide issue={i} onDecide={(d) => act(() => api.post(`/issues/${i.id}/decide`, { decision: d }), `#${i.id} 已記下你的決定`)} />
                    )}
                    {i.decision && i.status !== "needs_decision" && <Text label="你的決定" value={i.decision} />}
                    <Text label="處理方式" value={i.resolution} />
                    <dl className="kv-inline issue-refs">
                      {i.lemma && i.target_language && i.native_language && (
                        <span><dt>單字</dt><dd><Link to={`/words/${i.target_language}/${i.native_language}/${encodeURIComponent(i.lemma)}`}>{i.lemma}</Link></dd></span>
                      )}
                      {i.code_ref && <span><dt>程式位置</dt><dd className="mono">{i.code_ref}</dd></span>}
                      {i.spec_ref && <span><dt>規格</dt><dd>{i.spec_ref}</dd></span>}
                      <span><dt>回報者</dt><dd>{REPORTER[i.reporter] ?? i.reporter}</dd></span>
                      <span><dt>建立</dt><dd>{fmtTime(i.created_at)}</dd></span>
                      {i.resolved_at && <span><dt>結案</dt><dd>{fmtTime(i.resolved_at)}</dd></span>}
                    </dl>
                    {i.history.length > 0 && (
                      <details className="issue-history">
                        <summary>紀錄（{i.history.length}）</summary>
                        <ol>
                          {i.history.map((h, k) => (
                            <li key={k}>
                              <small className="muted">{fmtTime(h.at)} · {REPORTER[h.by] ?? h.by}</small>{" "}
                              {h.changes.map((c) => (
                                <span key={c.field} className="pill">
                                  {FIELD_LABEL[c.field] ?? c.field}：
                                  {c.field === "status" ? `${m.statuses[String(c.from)] ?? c.from ?? "—"} → ${m.statuses[String(c.to)] ?? c.to}` : String(c.to ?? "—").slice(0, 60)}
                                </span>
                              ))}
                              {h.note && <span>{h.note}</span>}
                            </li>
                          ))}
                        </ol>
                      </details>
                    )}
                    <div className="row-actions">
                      <button className="btn btn-small" onClick={() => setEditing(i)}>編輯</button>
                      {i.status !== "fixed" && i.kind !== "decision" && (
                        <button className="btn btn-small" onClick={() => act(() => api.put(`/issues/${i.id}`, { status: "fixed" }), `#${i.id} 標為已修正`)}>標為已修正</button>
                      )}
                      {(i.status === "fixed" || i.status === "wont_fix") && (
                        <button className="btn btn-small" onClick={() => act(() => api.put(`/issues/${i.id}`, { status: "open", note: "重新開啟" }), `#${i.id} 已重新開啟`)}>重新開啟</button>
                      )}
                      {i.status !== "wont_fix" && i.status !== "fixed" && (
                        <button className="btn btn-small btn-ghost" onClick={() => act(() => api.put(`/issues/${i.id}`, { status: "wont_fix" }), `#${i.id} 標為不處理`)}>不處理</button>
                      )}
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}

      {editing && m && (
        <IssueForm
          meta={m}
          issue={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(msg) => {
            setEditing(null);
            toast(msg);
            list.reload(true);
          }}
          onDelete={(id) => act(async () => { await api.del(`/issues/${id}`); setEditing(null); }, `#${id} 已刪除`)}
        />
      )}
      {node}
    </div>
  );
}

function Decide({ issue, onDecide }: { issue: Issue; onDecide: (d: string) => void }) {
  const [own, setOwn] = useState("");
  return (
    <div className="issue-decide">
      <h4>請你決定</h4>
      {(issue.options ?? []).length > 0 && (
        <div className="issue-options">
          {issue.options!.map((o, k) => (
            <button key={k} className="btn" onClick={() => onDecide(o)}>
              {o}
            </button>
          ))}
        </div>
      )}
      <div className="form-inline">
        <input className="input" placeholder="或寫下你的決定…" value={own} onChange={(e) => setOwn(e.target.value)} aria-label="你的決定" />
        <button className="btn btn-primary btn-small" disabled={!own.trim()} onClick={() => onDecide(own.trim())}>送出決定</button>
      </div>
    </div>
  );
}

function IssueForm({ meta, issue, onClose, onSaved, onDelete }: {
  meta: IssueMeta; issue: Issue | null; onClose: () => void; onSaved: (msg: string) => void; onDelete: (id: number) => void;
}) {
  const [f, setF] = useState<Form>(issue ? toForm(issue) : EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (issue) {
        await api.put(`/issues/${issue.id}`, fromForm(f));
        onSaved(`#${issue.id} 已儲存`);
      } else {
        const r = await api.post<Issue>("/issues", fromForm(f));
        onSaved(`已新增 #${r.id}`);
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const sel = (k: keyof Form, opts: Record<string, string>, label: string) => (
    <label className="field">
      <span>{label}</span>
      <select value={f[k]} onChange={set(k)}>
        {Object.entries(opts).map(([v, t]) => <option key={v} value={v}>{t}</option>)}
      </select>
    </label>
  );
  const area = (k: keyof Form, label: string, rows = 3, ph = "") => (
    <label className="field">
      <span>{label}</span>
      <textarea rows={rows} value={f[k]} onChange={set(k)} placeholder={ph} />
    </label>
  );
  return (
    <Modal
      title={issue ? `編輯 #${issue.id}` : "新增回報"}
      onClose={onClose}
      footer={
        <>
          {err && <span className="bad">{err}</span>}
          {issue && (
            <button className="btn btn-ghost" onClick={() => window.confirm(`刪除 #${issue.id}「${issue.title}」？刪除後無法復原。`) && onDelete(issue.id)}>
              刪除
            </button>
          )}
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn btn-primary" disabled={busy || !f.title.trim()} onClick={save}>{busy ? "儲存中…" : "儲存"}</button>
        </>
      }
    >
      <div className="issue-form">
        <label className="field wide">
          <span>標題</span>
          <input className="input" value={f.title} onChange={set("title")} autoFocus />
        </label>
        <div className="issue-form-row">
          {sel("kind", meta.kinds, "類型")}
          {sel("status", meta.statuses, "狀態")}
          {sel("severity", meta.severities, "嚴重度")}
          {sel("area", meta.areas, "範圍")}
        </div>
        {area("detail", "說明")}
        {area("steps", "重現步驟", 3, "1. …\n2. …")}
        <div className="grid2">
          {area("expected", "預期", 2)}
          {area("actual", "實際", 2)}
        </div>
        {(f.kind === "decision" || f.status === "needs_decision") && area("options", "給你選的選項（一行一個）", 3)}
        {area("resolution", "處理方式", 2)}
        <div className="issue-form-row">
          <label className="field"><span>單字</span><input className="input" value={f.lemma} onChange={set("lemma")} placeholder="apple" /></label>
          <label className="field"><span>目標語言</span><input className="input" value={f.target_language} onChange={set("target_language")} placeholder="en" /></label>
          <label className="field"><span>母語</span><input className="input" value={f.native_language} onChange={set("native_language")} placeholder="zh-TW" /></label>
        </div>
        <div className="issue-form-row">
          <label className="field"><span>程式位置</span><input className="input mono" value={f.code_ref} onChange={set("code_ref")} placeholder="app/lib/…:42" /></label>
          <label className="field"><span>規格</span><input className="input" value={f.spec_ref} onChange={set("spec_ref")} placeholder="spec-01 §7" /></label>
        </div>
        {issue && (
          <label className="field wide">
            <span>這次修改的說明（寫進紀錄）</span>
            <input className="input" value={f.note} onChange={set("note")} />
          </label>
        )}
      </div>
    </Modal>
  );
}
