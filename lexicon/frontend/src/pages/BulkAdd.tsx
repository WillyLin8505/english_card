import { useState } from "react";
import { api, newIdempotencyKey, type Job } from "../api";
import { ErrorBox, Link, PairPicker, Progress, useApp, useLoad } from "../ui";

// Card #753: 批量加入要學的單字（後台版的 App 一次加入多個）。
type Item = {
  typed: string;
  word: string;
  status: "existing" | "variant" | "new" | "typo" | "duplicate";
  pos: string;
  cefr: string | null;
  meaning: string;
  suggestion: string | null;
  include: boolean;
  phrase: boolean;
};
type Checked = { items: Item[]; over_limit: number; limit: number };
type Done = { added: number; existing: number; skipped: number; job_ids: number[]; wanted_list: string; wanted_total: number };

const LABEL: Record<Item["status"], string> = {
  existing: "詞庫已有",
  variant: "變化形 → 原形",
  new: "詞庫沒有 → 會新增並補資料",
  typo: "疑似錯字",
  duplicate: "重複（略過）",
};

function JobRow({ id }: { id: number }) {
  const job = useLoad<Job>(`/imports/${id}`, [id], 4000);
  const j = job.data;
  return (
    <li>
      <Link to={`/jobs/${id}`}>工作 #{id}</Link>：{j ? `${j.status}，${j.checkpoint}/${j.total}` : "載入中"}
      {j && <Progress value={j.total ? j.checkpoint / j.total : 0} />}
    </li>
  );
}

export default function BulkAdd() {
  const { target, native, langName } = useApp();
  const [text, setText] = useState("");
  const [res, setRes] = useState<Checked | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<Done | null>(null);
  const [idem, setIdem] = useState(newIdempotencyKey);

  const check = async () => {
    setBusy(true);
    setErr(null);
    setDone(null);
    try {
      const r = await api.post<Checked>("/bulk-add/check", { text, target_language: target, native_language: native });
      setRes(r);
      setItems(r.items);
    } catch (e) {
      setErr((e as Error).message);
    }
    setBusy(false);
  };

  const set = (i: number, patch: Partial<Item>) => setItems(items.map((x, k) => (k === i ? { ...x, ...patch } : x)));
  const take = async (i: number, word: string) => {
    // re-classify the corrected / edited word
    try {
      const r = await api.post<Checked>("/bulk-add/check", { text: word, target_language: target, native_language: native });
      if (r.items[0]) setItems(items.map((x, k) => (k === i ? { ...r.items[0], include: r.items[0].status !== "typo" } : x)));
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const picked = items.filter((x) => x.include && x.status !== "duplicate");
  const nNew = picked.filter((x) => x.status === "new" || x.status === "typo").length;
  const nHave = picked.length - nNew;

  const confirm = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.post<Done>(
        "/bulk-add/confirm",
        { target_language: target, native_language: native, items: items.map((x) => ({ word: x.word, include: x.include && x.status !== "duplicate" })) },
        { "Idempotency-Key": idem },
      );
      setDone(r);
      setRes(null);
      setItems([]);
      setText("");
      setIdem(newIdempotencyKey());
    } catch (e) {
      setErr((e as Error).message);
    }
    setBusy(false);
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>批量加入單字</h1>
          <p className="muted">貼上要學的單字：一行一個，也可用逗號、頓號、Tab 分隔（可從 Excel 貼上），一次最多 500 個。</p>
        </div>
      </header>
      <section className="form-section">
        <h2>學習語言</h2>
        <PairPicker />
        <p className="muted">目前：{langName(target)} → {langName(native)}</p>
      </section>
      {err && <ErrorBox error={err} />}
      {done && (
        <section className="form-section">
          <h2>完成：新增 {done.added}、已有 {done.existing}、略過 {done.skipped}</h2>
          <p className="muted">全部已記進字表「{done.wanted_list}」（共 {done.wanted_total} 個）。新字已排進補資料佇列（翻譯、例句、音檔、圖片；AI 部分交給 Qwen）：</p>
          <ul>{done.job_ids.map((id) => <JobRow key={id} id={id} />)}</ul>
        </section>
      )}
      {!res ? (
        <section className="form-section">
          <textarea className="input" rows={12} value={text} onChange={(e) => setText(e.target.value)} placeholder={"balcony\nbrewed\npick up\nrecieve"} />
          <p>
            <button className="btn primary" disabled={busy || !text.trim()} onClick={check}>檢查</button>
          </p>
        </section>
      ) : (
        <section className="form-section">
          {res.over_limit > 0 && <p className="warn">超過 {res.limit} 個，後面的 {res.over_limit} 個沒有檢查。</p>}
          <table className="table">
            <thead>
              <tr><th>加入</th><th>輸入</th><th>狀態</th><th>字</th><th>詞性</th><th>CEFR</th><th>中文</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((x, i) => (
                <tr key={i}>
                  <td><input type="checkbox" checked={x.include && x.status !== "duplicate"} disabled={x.status === "duplicate"} onChange={(e) => set(i, { include: e.target.checked })} /></td>
                  <td>{x.typed}</td>
                  <td>{LABEL[x.status]}{x.phrase && x.status === "new" ? "（片語）" : ""}</td>
                  <td>
                    <input className="input" size={14} defaultValue={x.word} key={x.word + i} onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== x.word) take(i, v); }} />
                  </td>
                  <td>{x.pos}</td>
                  <td>{x.cefr ?? ""}</td>
                  <td>{x.meaning}</td>
                  <td>{x.status === "typo" && x.suggestion && <button className="btn" onClick={() => take(i, x.suggestion!)}>改成 {x.suggestion}</button>}
                    {x.status === "typo" && <button className="btn" onClick={() => set(i, { include: true, status: "new" })}>照原樣新增</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            <button className="btn" onClick={() => setRes(null)}>返回修改</button>{" "}
            <button className="btn primary" disabled={busy || !picked.length} onClick={confirm}>
              確認：新增 {nNew}、已有 {nHave}
            </button>
          </p>
        </section>
      )}
    </div>
  );
}
