import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { api, type Overview, type Policy, type Step, type TestResult } from "../api";
import { Chip, Empty, ErrorBox, Loading, Modal, PairPicker, summarize, useApp, useLoad, useToast } from "../ui";

const STRATEGY_HELP: Record<string, string> = {
  FIRST_VALID: "採用第一個有有效值的來源；之後的來源不再查詢。",
  MERGE_UNIQUE: "依順位查詢所有來源，合併並去除重複。",
  FILL_MISSING: "逐項補缺：每個項目（詞義、例句、單字…）採用第一個有它的來源；沒有缺項就不再往下查。",
  BEST_SCORE: "查詢所有來源，每個項目採用可信度最高的值（同分取順位較前者）。",
  APPEND_LIMITED: "依順位附加結果，達到欄位上限就停止查詢後面的來源。",
};

type Draft = { strategy: string; max_items: number | null; steps: Step[] };

function toDraft(p: Policy): Draft {
  return {
    strategy: p.strategy ?? "FIRST_VALID",
    max_items: p.max_items,
    steps: p.steps.map((s) => ({ ...s })),
  };
}

function body(d: Draft) {
  return {
    strategy: d.strategy,
    max_items: d.max_items,
    steps: d.steps.map((s) => ({
      source: s.source,
      enabled: s.enabled,
      timeout_s: s.timeout_s,
      retries: s.retries,
      min_confidence: s.min_confidence,
      max_results: s.max_results,
      continue_on_failure: s.continue_on_failure,
    })),
  };
}

const same = (a: Draft, b: Draft) => JSON.stringify(body(a)) === JSON.stringify(body(b));

export default function Policies({ route }: { route: string }) {
  const { target, native, langName } = useApp();
  const initial = new URLSearchParams(route.split("?")[1] || "").get("field");
  const [selected, setSelectedState] = useState<string | null>(initial);
  useEffect(() => {
    if (initial) setSelectedState(initial);
  }, [initial]);
  // Keep the selection in the address so it can be linked and reloaded.
  const setSelected = (f: string) => {
    setSelectedState(f);
    history.replaceState(null, "", `#/policies?field=${f}`);
  };
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  // Unsaved edits per field, kept while other fields are selected.
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [filter, setFilter] = useState<"all" | "unset" | "attention">("all");
  const ov = useLoad<Overview>(`/policies/${target}/${native}`, [target, native]);

  useEffect(() => {
    setDrafts({});
  }, [target, native]);

  const stash = useCallback((field: string, d: Draft | null) => {
    setDrafts((all) => {
      if (!d && !(field in all)) return all;
      const n = { ...all };
      if (d) n[field] = d;
      else delete n[field];
      return n;
    });
  }, []);

  const rows = ov.data?.blocks.flatMap((b) => b.fields) ?? [];
  const selectedRow = rows.find((r) => r.field === selected);
  const totals = ov.data?.blocks.reduce(
    (acc, b) => ({ unset: acc.unset + b.counts.unset, attention: acc.attention + b.counts.attention, total: acc.total + b.counts.total }),
    { unset: 0, attention: 0, total: 0 },
  );

  return (
    <div className="page page-wide">
      <header className="page-head">
        <div>
          <h1>來源順位（Source Policies）</h1>
          <p className="muted">
            每個細項都是獨立的 Policy（目標語言＋母語＋欄位）。拖曳只改變目前細項；沒有來源的細項是「未設定」，不會繼承其他細項。
          </p>
        </div>
        <PairPicker />
      </header>
      {ov.error && <ErrorBox error={ov.error} onRetry={() => ov.reload()} />}
      {!ov.data && !ov.error && <Loading />}
      {ov.data && (
        <div className="policy-layout">
          <section className="policy-list" aria-label="資料區塊">
            <div className="toolbar">
              <div className="seg" role="tablist" aria-label="篩選">
                {(
                  [
                    ["all", `全部 ${totals?.total ?? 0}`],
                    ["unset", `未設定 ${totals?.unset ?? 0}`],
                    ["attention", `需注意 ${totals?.attention ?? 0}`],
                  ] as const
                ).map(([k, label]) => (
                  <button key={k} role="tab" aria-selected={filter === k} className={filter === k ? "on" : ""} onClick={() => setFilter(k)}>
                    {label}
                  </button>
                ))}
              </div>
              <button className="btn btn-small" onClick={() => setCollapsed(collapsed.size ? new Set() : new Set(ov.data!.blocks.map((b) => b.block)))}>
                {collapsed.size ? "全部展開" : "全部收合"}
              </button>
            </div>
            {ov.data.blocks.map((b) => {
              const open = !collapsed.has(b.block);
              const shown = b.fields.filter((f) => filter === "all" || f.status === filter);
              if (!shown.length && filter !== "all") return null;
              return (
                <div key={b.block} className="block">
                  <button
                    className="block-head"
                    aria-expanded={open}
                    onClick={() => {
                      const n = new Set(collapsed);
                      if (open) n.add(b.block);
                      else n.delete(b.block);
                      setCollapsed(n);
                    }}
                  >
                    <span className="caret" aria-hidden>
                      {open ? "▾" : "▸"}
                    </span>
                    <strong>{b.label}</strong>
                    <span className="block-counts">
                      完成 {b.counts.configured}/{b.counts.total}
                      {b.counts.unset > 0 && <span className="bad"> · 未設定 {b.counts.unset}</span>}
                      {b.counts.attention > 0 && <span className="warn"> · 需注意 {b.counts.attention}</span>}
                      {b.counts.errors > 0 && <span className="bad"> · 錯誤 {b.counts.errors}</span>}
                    </span>
                  </button>
                  {open && (
                    <ul className="field-rows">
                      {shown.map((f) => (
                        <li key={f.field}>
                          <button className={`field-row ${selected === f.field ? "selected" : ""}`} onClick={() => setSelected(f.field)} aria-current={selected === f.field}>
                            <span className="fr-label">
                              {f.label}
                              <span className={`scope scope-${f.scope}`}>{f.scope === "native" ? `母語 ${langName(native)}` : `目標 ${langName(target)}`}</span>
                              {f.field in drafts && <span className="unsaved">未儲存</span>}
                            </span>
                            <span className="fr-status">
                              <Chip status={f.status} />
                            </span>
                            <span className="fr-first">
                              {f.first_source_name ?? <span className="bad">沒有來源</span>}
                              {f.backups > 0 && <span className="muted"> ＋{f.backups} 備援</span>}
                            </span>
                            <span className="fr-strategy">{f.strategy ?? "—"}{f.max_items ? ` · 上限 ${f.max_items}` : ""}</span>
                            <span className="fr-test">
                              {f.last_test ? (
                                <>
                                  測「{f.last_test.word}」<Chip status={f.last_test.status} />
                                </>
                              ) : (
                                <span className="muted">未測試</span>
                              )}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </section>
          <aside className="policy-panel" aria-label="細項設定">
            {selectedRow ? (
              <PolicyEditor key={`${target}-${native}-${selectedRow.field}`} field={selectedRow.field} onChanged={() => ov.reload(true)} stashed={drafts[selectedRow.field]} onStash={stash} />
            ) : (
              <Empty>
                在左側點選一個細項，拖曳調整它的來源順位、設定策略並測試單字。
              </Empty>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}

// ── Editor for one field ────────────────────────────────────────────

function PolicyEditor({ field, onChanged, stashed, onStash }: { field: string; onChanged: () => void; stashed?: Draft; onStash: (f: string, d: Draft | null) => void }) {
  const { target, native, meta } = useApp();
  const path = `/policies/${target}/${native}/${field}`;
  const pol = useLoad<Policy>(path, [path]);
  const [saved, setSaved] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [openStep, setOpenStep] = useState<string | null>(null);
  const [copyOpen, setCopyOpen] = useState(false);
  const [confirmDefault, setConfirmDefault] = useState(false);
  const { toast, node } = useToast();

  useEffect(() => {
    if (pol.data) {
      setSaved(toDraft(pol.data));
      setDraft((d) => d ?? stashed ?? toDraft(pol.data!));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pol.data]);

  const isDirty = !!(saved && draft && !same(saved, draft));
  useEffect(() => {
    if (saved && draft) onStash(field, isDirty ? draft : null);
  }, [field, saved, draft, isDirty, onStash]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  const save = async (d: Draft, what: string) => {
    setBusy(true);
    setErr(null);
    try {
      const p = await api.put<Policy>(path, { ...body(d), expected_version: pol.data?.version });
      pol.setData(p);
      onChanged();
      toast(`${what}已儲存（版本 ${p.version}）`);
      return p;
    } catch (e) {
      setErr((e as Error).message);
      pol.reload(true);
      return null;
    } finally {
      setBusy(false);
    }
  };

  // Dragging saves at once: the saved settings with the new order only.
  const onDragEnd = async (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id || !draft || !saved) return;
    const ids = draft.steps.map((s) => s.source);
    const from = ids.indexOf(String(e.active.id));
    const to = ids.indexOf(String(e.over.id));
    const newDraft = { ...draft, steps: arrayMove(draft.steps, from, to) };
    setDraft(newDraft);
    const order = newDraft.steps.map((s) => s.source);
    const savedSteps = [...saved.steps].sort((a, b) => {
      const ia = order.indexOf(a.source), ib = order.indexOf(b.source);
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
    });
    const p = await save({ ...saved, steps: savedSteps }, "新順位");
    if (p) {
      const s = toDraft(p);
      setSaved(s);
      // keep other unsaved edits, in the new order
      setDraft({ ...newDraft });
    }
  };

  const update = (src: string, patch: Partial<Step>) =>
    setDraft((d) => d && { ...d, steps: d.steps.map((s) => (s.source === src ? { ...s, ...patch } : s)) });

  if (pol.error) return <ErrorBox error={pol.error} onRetry={() => pol.reload()} />;
  if (!pol.data || !draft) return <Loading />;
  const p = pol.data;
  const inDraft = new Set(draft.steps.map((s) => s.source));
  const available = [...p.available, ...(saved?.steps ?? []).filter((s) => !inDraft.has(s.source)).map((s) => ({ source: s.source, name: s.name ?? s.source, kind: s.kind ?? "", license: s.license ?? "", implemented: s.implemented ?? true, note: "" }))].filter((s) => !inDraft.has(s.source));
  const enabled = draft.steps.filter((s) => s.enabled);

  return (
    <div className="editor">
      {node}
      <header className="editor-head">
        <div>
          <h2>{p.label}</h2>
          <p className="muted">
            {meta.blocks.find((b) => b.key === p.block)?.label} · {p.scope === "native" ? "母語資料（每個語言方向各自一份）" : "目標語言資料（候選值可被各母語共用）"} · 版本 {p.version}
          </p>
          {p.description && <p className="muted">{p.description}</p>}
        </div>
        <div className="editor-status">
          {enabled.length === 0 ? <Chip status="unset" /> : <Chip status={p.status} />}
          {isDirty && <span className="unsaved">未儲存</span>}
        </div>
      </header>
      {err && <ErrorBox error={err} />}

      <section>
        <h3>已啟用來源（第一順位在最上面）</h3>
        {draft.steps.length === 0 ? (
          <Empty>未設定：這個細項沒有任何來源，擷取時會標成「未設定」，不會呼叫其他區塊的來源。</Empty>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={draft.steps.map((s) => s.source)} strategy={verticalListSortingStrategy}>
              <ol className="steps">
                {draft.steps.map((s, i) => (
                  <SortableStep
                    key={s.source}
                    step={s}
                    rank={i + 1}
                    open={openStep === s.source}
                    onToggleOpen={() => setOpenStep(openStep === s.source ? null : s.source)}
                    onChange={(patch) => update(s.source, patch)}
                    onRemove={() => setDraft({ ...draft, steps: draft.steps.filter((x) => x.source !== s.source) })}
                    disabled={busy}
                  />
                ))}
              </ol>
            </SortableContext>
          </DndContext>
        )}
        <p className="hint">拖曳 ⠿ 或用鍵盤（聚焦後按空白鍵、方向鍵、空白鍵）調整順位；放開後立即以單一交易儲存。</p>
      </section>

      <section>
        <h3>可加入來源</h3>
        {available.length === 0 ? (
          <p className="muted">沒有其他宣告支援這個欄位與語言方向的來源。</p>
        ) : (
          <ul className="source-options">
            {available.map((s) => (
              <li key={s.source}>
                <span>
                  <strong>{s.name}</strong> <span className="kind">{s.kind}</span>
                  {!s.implemented && <span className="warn"> · adapter 尚未實作</span>}
                  <br />
                  <small className="muted">{s.license}</small>
                </span>
                <button
                  className="btn btn-small"
                  onClick={() =>
                    setDraft({
                      ...draft,
                      steps: [
                        ...draft.steps,
                        { source: s.source, name: s.name, kind: s.kind, implemented: s.implemented, license: s.license, enabled: true, timeout_s: s.kind === "ai" ? 120 : 20, retries: s.kind === "ai" ? 1 : 2, min_confidence: 0, max_results: null, continue_on_failure: true },
                      ],
                    })
                  }
                >
                  加入
                </button>
              </li>
            ))}
          </ul>
        )}
        {p.unsupported.length > 0 && (
          <details className="unsupported">
            <summary>不支援這個欄位／方向的來源（{p.unsupported.length}）</summary>
            <ul>
              {p.unsupported.map((s) => (
                <li key={s.source}>
                  <strong>{s.name}</strong>：{s.reason}
                  {s.note && <small className="muted"> — {s.note}</small>}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <section className="grid2">
        <label className="field">
          <span>合併策略</span>
          <select value={draft.strategy} onChange={(e) => setDraft({ ...draft, strategy: e.target.value })}>
            {Object.entries(meta.strategies).map(([k, v]) => (
              <option key={k} value={k}>
                {k} — {v}
              </option>
            ))}
          </select>
          <small className="muted">{STRATEGY_HELP[draft.strategy]}</small>
        </label>
        <label className="field">
          <span>欄位上限（筆）</span>
          <input
            className="input"
            type="number"
            min={1}
            max={200}
            placeholder="不限"
            value={draft.max_items ?? ""}
            onChange={(e) => setDraft({ ...draft, max_items: e.target.value ? Number(e.target.value) : null })}
          />
          <small className="muted">APPEND_LIMITED 達到上限就不再查詢後面的來源。</small>
        </label>
      </section>

      <div className="actions">
        <button className="btn btn-primary" disabled={!isDirty || busy} onClick={async () => {
          const r = await save(draft, "設定");
          if (r) {
            setSaved(toDraft(r));
            setDraft(toDraft(r));
          }
        }}>
          儲存變更
        </button>
        <button className="btn" disabled={!isDirty || busy} onClick={() => saved && setDraft(saved)}>
          捨棄變更
        </button>
        <button className="btn" disabled={busy} onClick={() => setCopyOpen(true)}>
          複製此順位到⋯
        </button>
        <button className="btn btn-ghost" disabled={busy} onClick={() => setConfirmDefault(true)}>
          恢復預設
        </button>
      </div>

      <TestPanel field={field} draft={isDirty ? draft : null} onTested={onChanged} />

      {copyOpen && <CopyDialog field={field} label={p.label} onClose={() => setCopyOpen(false)} onDone={(n) => { setCopyOpen(false); onChanged(); toast(`已套用到 ${n} 個細項`); }} />}
      {confirmDefault && (
        <Modal
          title={`恢復「${p.label}」的預設順位？`}
          onClose={() => setConfirmDefault(false)}
          footer={
            <>
              <button className="btn" onClick={() => setConfirmDefault(false)}>取消</button>
              <button
                className="btn btn-primary"
                onClick={async () => {
                  setConfirmDefault(false);
                  try {
                    const r = await api.post<Policy>(`${path}/restore-default`);
                    pol.setData(r);
                    setDraft(toDraft(r));
                    onChanged();
                    toast("已恢復預設");
                  } catch (e) {
                    setErr((e as Error).message);
                  }
                }}
              >
                恢復預設
              </button>
            </>
          }
        >
          <p>只會改變這一個細項，其他細項不受影響。</p>
          <p>
            預設：{p.default.sources.length ? p.default.sources.map((s) => (<span key={s} className="pill">{s}</span>)) : <span className="bad">未設定（沒有支援這個方向的預設來源）</span>}
            · {p.default.strategy}
            {p.default.max_items ? ` · 上限 ${p.default.max_items}` : ""}
          </p>
        </Modal>
      )}
    </div>
  );
}

function SortableStep({ step, rank, open, onToggleOpen, onChange, onRemove, disabled }: {
  step: Step;
  rank: number;
  open: boolean;
  onToggleOpen: () => void;
  onChange: (p: Partial<Step>) => void;
  onRemove: () => void;
  disabled: boolean;
}) {
  const { sourceName } = useApp();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: step.source, disabled });
  const style = { transform: CSS.Transform.toString(transform), transition };
  return (
    <li ref={setNodeRef} style={style} className={`step ${isDragging ? "dragging" : ""} ${step.enabled ? "" : "step-off"}`}>
      <div className="step-main">
        <button className="handle" {...attributes} {...listeners} aria-label={`拖曳 ${sourceName(step.source)}，目前第 ${rank} 順位`}>
          ⠿
        </button>
        <span className="rank">{rank}</span>
        <span className="step-name">
          <strong>{step.name ?? sourceName(step.source)}</strong>
          {step.implemented === false && <span className="warn"> · adapter 尚未實作（會被略過）</span>}
          <small className="muted">
            逾時 {step.timeout_s}s · 重試 {step.retries} · 最低可信度 {step.min_confidence}
            {step.max_results ? ` · 最多 ${step.max_results} 筆` : ""}
            {step.continue_on_failure ? "" : " · 失敗即停止"}
          </small>
        </span>
        <label className="switch" title={step.enabled ? "停用" : "啟用"}>
          <input type="checkbox" checked={step.enabled} onChange={(e) => onChange({ enabled: e.target.checked })} />
          <span>{step.enabled ? "啟用" : "停用"}</span>
        </label>
        <button className="btn btn-small" onClick={onToggleOpen} aria-expanded={open}>
          設定
        </button>
        <button className="btn btn-small btn-ghost" onClick={onRemove} aria-label={`移除 ${sourceName(step.source)}`}>
          移除
        </button>
      </div>
      {open && (
        <div className="step-settings">
          <label>
            逾時（秒）
            <input className="input" type="number" min={1} max={600} value={step.timeout_s} onChange={(e) => onChange({ timeout_s: Number(e.target.value) })} />
          </label>
          <label>
            重試次數
            <input className="input" type="number" min={0} max={10} value={step.retries} onChange={(e) => onChange({ retries: Number(e.target.value) })} />
          </label>
          <label>
            最低可信度
            <input className="input" type="number" min={0} max={1} step={0.05} value={step.min_confidence} onChange={(e) => onChange({ min_confidence: Number(e.target.value) })} />
          </label>
          <label>
            最大結果數
            <input className="input" type="number" min={1} max={200} placeholder="不限" value={step.max_results ?? ""} onChange={(e) => onChange({ max_results: e.target.value ? Number(e.target.value) : null })} />
          </label>
          <label className="check">
            <input type="checkbox" checked={step.continue_on_failure} onChange={(e) => onChange({ continue_on_failure: e.target.checked })} />
            這個來源失敗時繼續下一個
          </label>
        </div>
      )}
    </li>
  );
}

// ── Test a word ─────────────────────────────────────────────────────

function TestPanel({ field, draft, onTested }: { field: string; draft: Draft | null; onTested: () => void }) {
  const { target, native, langName } = useApp();
  const [word, setWord] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [res, setRes] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    if (!word.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await api.post<TestResult>(`/policies/${target}/${native}/${field}/test`, { word, refresh, draft: draft ? body(draft) : null });
      setRes(r);
      onTested();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="test">
      <h3>測試單字</h3>
      <form
        className="test-form"
        onSubmit={(e) => {
          e.preventDefault();
          run();
        }}
      >
        <input className="input" placeholder={target === "en" ? "例如 apple、go、happy" : "輸入單字"} value={word} onChange={(e) => setWord(e.target.value)} aria-label="測試單字" />
        <button className="btn btn-primary" disabled={busy || !word.trim()}>
          {busy ? "測試中…" : draft ? "用未儲存設定測試" : "測試"}
        </button>
        <label className="check">
          <input type="checkbox" checked={refresh} onChange={(e) => setRefresh(e.target.checked)} /> 略過快取
        </label>
      </form>
      <p className="hint">只執行這個細項（缺少的依賴欄位用已儲存的順位補上），不寫入詞庫。</p>
      {busy && <Loading what="查詢來源中（新單字可能要幾十秒）" />}
      {err && <ErrorBox error={err} />}
      {res && !busy && (
        <div className="test-result">
          <div className="test-summary">
            <Chip status={res.status} /> 「{res.word}」採用 {res.items.length} 筆
            {res.missing.length > 0 && <span className="warn"> · 仍缺 {res.missing.length} 項</span>}
            {res.draft && <span className="unsaved">未儲存設定</span>}
          </div>
          {res.dependencies.length > 0 && (
            <p className="muted">
              依賴欄位：
              {res.dependencies.map((d) => (
                <span key={d.field} className="pill">
                  {d.label} {d.count} 筆（{d.from === "stored" ? "已存" : "即時"}）
                </span>
              ))}
            </p>
          )}
          {res.items.length > 0 && (
            <div className="adopted">
              <strong>最後採用值</strong>
              <ol>
                {res.items.map((it, i) => (
                  <li key={i}>
                    {summarize(it)} <span className="src">{String(it.source)}</span>
                    {Boolean(it.ai) && <span className="ai">AI 翻譯</span>}
                  </li>
                ))}
              </ol>
            </div>
          )}
          {res.pairs.length > 0 && (
            <table className="table pairs">
              <caption>雙語預覽</caption>
              <thead>
                <tr>
                  <th>#</th>
                  <th>{langName(target)}</th>
                  <th>{langName(native)}</th>
                  <th>來源</th>
                </tr>
              </thead>
              <tbody>
                {res.pairs.map((p) => (
                  <tr key={p.n}>
                    <td>{p.n}</td>
                    <td>{p.target}</td>
                    <td>{p.native ?? <span className="bad">缺{langName(native)}</span>}</td>
                    <td>
                      {p.source ?? "—"}
                      {p.ai && <span className="ai">AI</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h4>逐來源結果</h4>
          {res.steps.map((s, i) => (
            <div key={s.source} className={`step-result step-result-${s.status}`}>
              <div className="sr-head">
                <span className="rank">{i + 1}</span>
                <strong>{s.name}</strong>
                <Chip status={s.status === "skipped" ? "skipped" : s.status} label={s.status === "skipped" ? "未查詢" : undefined} />
                {s.reason && <span className="muted">{s.reason}</span>}
                {s.status !== "skipped" && (
                  <span className="muted">
                    {s.ms} ms · 候選 {s.candidates.length}、有效 {s.valid_count}、採用 {s.adopted}
                  </span>
                )}
              </div>
              {s.candidates.length > 0 && (
                <table className="table compact">
                  <thead>
                    <tr>
                      <th>正規化結果</th>
                      <th>可信度</th>
                      <th>驗證</th>
                      <th>採用</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.candidates.slice(0, 40).map((c, j) => (
                      <tr key={j} className={c.valid ? "" : "invalid"}>
                        <td>{summarize(c.value)}</td>
                        <td>{c.confidence}</td>
                        <td>{c.valid ? "通過" : <span className="bad">{c.invalid_reason}</span>}</td>
                        <td>{c.adopted ? "✓" : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {s.raw !== null && s.raw !== undefined && (
                <details>
                  <summary>原始結果</summary>
                  <pre className="raw">{typeof s.raw === "string" ? s.raw : JSON.stringify(s.raw, null, 1)}</pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

// ── 複製此順位到⋯ ─────────────────────────────────────────────────

type CopyPlan = { confirmed: boolean; plan: { field: string; label: string; steps: Step[]; dropped: { source: string; reason: string }[] }[] };

function CopyDialog({ field, label, onClose, onDone }: { field: string; label: string; onClose: () => void; onDone: (n: number) => void }) {
  const { target, native, meta } = useApp();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [plan, setPlan] = useState<CopyPlan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fields = useMemo(() => meta.fields.filter((f) => f.key !== field && (!f.languages || f.languages.includes(target))), [meta, field, target]);
  const path = `/policies/${target}/${native}/${field}/copy`;

  const preview = async () => {
    try {
      setErr(null);
      setPlan(await api.post<CopyPlan>(path, { to_fields: [...picked], confirm: false }));
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const apply = async () => {
    try {
      const r = await api.post<CopyPlan>(path, { to_fields: [...picked], confirm: true });
      onDone(r.plan.length);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <Modal
      title={`複製「${label}」的順位到⋯`}
      onClose={onClose}
      footer={
        plan ? (
          <>
            <button className="btn" onClick={() => setPlan(null)}>返回選擇</button>
            <button className="btn btn-primary" onClick={apply}>確認套用到 {plan.plan.length} 個細項</button>
          </>
        ) : (
          <button className="btn btn-primary" disabled={!picked.size} onClick={preview}>
            預覽（{picked.size}）
          </button>
        )
      }
    >
      {err && <ErrorBox error={err} />}
      {!plan ? (
        <div className="copy-pick">
          <p className="muted">只有勾選並確認的細項會被覆蓋；每個細項只保留它支援的來源。</p>
          {meta.blocks.map((b) => {
            const fs = fields.filter((f) => f.block === b.key);
            if (!fs.length) return null;
            return (
              <fieldset key={b.key}>
                <legend>{b.label}</legend>
                {fs.map((f) => (
                  <label key={f.key} className="check">
                    <input
                      type="checkbox"
                      checked={picked.has(f.key)}
                      onChange={(e) => {
                        const n = new Set(picked);
                        if (e.target.checked) n.add(f.key);
                        else n.delete(f.key);
                        setPicked(n);
                      }}
                    />
                    {f.label}
                  </label>
                ))}
              </fieldset>
            );
          })}
        </div>
      ) : (
        <ul className="copy-plan">
          {plan.plan.map((p) => (
            <li key={p.field}>
              <strong>{p.label}</strong>：{p.steps.length ? p.steps.map((s) => <span key={s.source} className="pill">{s.name ?? s.source}</span>) : <span className="bad">沒有可用來源 → 會變成「未設定」</span>}
              {p.dropped.length > 0 && (
                <div className="warn">略過：{p.dropped.map((d) => `${d.source}（${d.reason}）`).join("、")}</div>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="hint">複製不會改變沒有勾選的細項。</p>
    </Modal>
  );
}
