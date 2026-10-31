import { useState } from "react";
import { api } from "../api";
import { Modal, useLoad } from "../ui";

// The 問題回報 parts of the 控制台 (card #919): a report's screenshot, the decide box and the form.

type HistoryEntry = { at: string; by: string; note: string | null; changes: { field: string; from: unknown; to: unknown }[] };
export function Screenshot({ id }: { id: number }) {
  const one = useLoad<{ screenshot: string | null }>(`/issues/${id}`);
  if (!one.data?.screenshot) return null;
  return (
    <div className="issue-field">
      <small className="muted">附件截圖</small>
      <a href={one.data.screenshot} target="_blank" rel="noreferrer">
        <img src={one.data.screenshot} alt="App 回報截圖" style={{ maxWidth: 320, maxHeight: 480, display: "block" }} />
      </a>
    </div>
  );
}

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
  has_screenshot?: boolean;
  history: HistoryEntry[];
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  stage?: string | null;
  stage_state?: string | null;
};
export type IssueMeta = { kinds: Record<string, string>; statuses: Record<string, string>; severities: Record<string, string>; areas: Record<string, string> };

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

export function Decide({ issue, onDecide }: { issue: Issue; onDecide: (d: string) => void }) {
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
        <input className="input" placeholder="其他：以上都不滿意，寫下你要的…" value={own} onChange={(e) => setOwn(e.target.value)} aria-label="你的決定" />
        <button className="btn btn-primary btn-small" disabled={!own.trim()} onClick={() => onDecide(own.trim())}>送出決定</button>
      </div>
    </div>
  );
}

export function IssueForm({ meta, issue, onClose, onSaved, onDelete }: {
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
