import { useEffect, useMemo, useState } from "react";
import { api, newIdempotencyKey, type Job } from "../api";
import { ErrorBox, Loading, PairPicker, Rate, fmtBytes, useApp, useLoad } from "../ui";

type Wordlist = { id: number; language: string; name: string; count: number; words: string[] };
type Estimate = {
  words: number;
  fields: number;
  note: string;
  target: EstimateScope;
  native: EstimateScope;
  audio: { files: number; requests_upper_bound: number; storage_bytes: number };
  images: { files: number; requests_upper_bound: number; storage_bytes: number; ai_label_seconds: number };
};
type EstimateScope = {
  fields: number;
  cells: number;
  already_complete: number;
  to_process: number;
  current_completeness: number;
  expected_completeness: number;
  requests_upper_bound: number;
  storage_bytes: number;
};

const MODE_HELP: Record<string, string> = {
  fill_missing: "只處理還不完整、或順位改過的欄位；已完成的跳過。",
  force_refresh: "不使用快取，重新向每個來源查詢。",
  validate_only: "不查詢來源，用目前規則重新驗證已存的候選值。",
  dry_run: "照常查詢與合併，但不寫入詞庫；用來先看結果與錯誤。",
  reresolve: "用已存的候選值依目前順位重新選值；沒查過的來源才會查。",
};

export default function StartImport() {
  const { meta, target, native, langName } = useApp();
  const lists = useLoad<Wordlist[]>(`/wordlists?language=${target}`, [target]);
  const [wordlist, setWordlist] = useState("");
  const [custom, setCustom] = useState("");
  // Fetching writes to the lexicon; 乾跑 (preview only) is a choice, not the default.
  const [mode, setMode] = useState("fill_missing");
  const fieldsForTarget = useMemo(() => meta.fields.filter((f) => !f.languages || f.languages.includes(target)), [meta, target]);
  const [fields, setFields] = useState<Set<string>>(new Set());
  const [limitSources, setLimitSources] = useState(false);
  const { sources } = useApp();
  const [picked, setPicked] = useState<Set<string>>(new Set(Object.keys(sources)));
  const [est, setEst] = useState<Estimate | null>(null);
  const [estErr, setEstErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [idem] = useState(newIdempotencyKey);

  useEffect(() => {
    // Every field, sense pictures included: they are fetched automatically.
    setFields(new Set(fieldsForTarget.map((f) => f.key)));
  }, [fieldsForTarget]);

  const words = custom.split(/[\n,，、]+/).map((w) => w.trim()).filter(Boolean);
  const bodyObj = {
    target_language: target,
    native_language: native,
    mode,
    wordlist: wordlist || null,
    words,
    fields: [...fields],
    sources: limitSources ? [...picked] : null,
    parallelism: 4,
  };
  const bodyKey = JSON.stringify(bodyObj);
  const hasWords = !!wordlist || words.length > 0;

  useEffect(() => {
    if (!hasWords || !fields.size) {
      setEst(null);
      return;
    }
    const t = setTimeout(async () => {
      try {
        setEstErr(null);
        setEst(await api.post<Estimate>("/imports/estimate", bodyObj));
      } catch (e) {
        setEstErr((e as Error).message);
      }
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey, hasWords]);

  const start = async () => {
    setBusy(true);
    setErr(null);
    try {
      const job = await api.post<Job>("/imports", bodyObj, { "Idempotency-Key": idem });
      window.location.hash = `/jobs/${job.id}`;
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  const toggleBlock = (block: string, on: boolean) => {
    const n = new Set(fields);
    fieldsForTarget.filter((f) => f.block === block).forEach((f) => (on ? n.add(f.key) : n.delete(f.key)));
    setFields(n);
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>開始擷取（Start Import Job）</h1>
          <p className="muted">目標語言與母語都必填。大型工作會自動分成 4 份平行處理；關掉瀏覽器也會繼續。</p>
        </div>
      </header>
      <section className="form-section">
        <h2>1. 語言方向</h2>
        <PairPicker />
      </section>
      <section className="form-section">
        <h2>2. 單字範圍</h2>
        {lists.error && <ErrorBox error={lists.error} />}
        {!lists.data ? (
          <Loading />
        ) : (
          <div className="grid2">
            <label className="field">
              <span>字表</span>
              <select value={wordlist} onChange={(e) => setWordlist(e.target.value)}>
                <option value="">（不使用字表）</option>
                {lists.data.map((l) => (
                  <option key={l.id} value={l.name}>
                    {l.name}（{l.count}）
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>自訂單字（換行或逗號分隔）</span>
              <textarea className="input" rows={4} value={custom} onChange={(e) => setCustom(e.target.value)} placeholder={"apple\nhappy\ngo"} />
            </label>
          </div>
        )}
      </section>
      <section className="form-section">
        <h2>3. 精確欄位（{fields.size}）</h2>
        <div className="field-picker">
          {meta.blocks.map((b) => {
            const fs = fieldsForTarget.filter((f) => f.block === b.key);
            if (!fs.length) return null;
            const all = fs.every((f) => fields.has(f.key));
            return (
              <fieldset key={b.key}>
                <legend>
                  <label className="check">
                    <input type="checkbox" checked={all} onChange={(e) => toggleBlock(b.key, e.target.checked)} />
                    {b.label}
                  </label>
                </legend>
                {fs.map((f) => (
                  <label key={f.key} className="check">
                    <input
                      type="checkbox"
                      checked={fields.has(f.key)}
                      onChange={(e) => {
                        const n = new Set(fields);
                        if (e.target.checked) n.add(f.key);
                        else n.delete(f.key);
                        setFields(n);
                      }}
                    />
                    {f.label}
                    {f.scope === "native" && <span className="scope scope-native">母語</span>}
                  </label>
                ))}
              </fieldset>
            );
          })}
        </div>
        <p className="hint">依賴欄位會自動一起處理（例如只選「母語翻譯」時，缺少的例句會先依例句順位取得）。</p>
      </section>
      <section className="form-section">
        <h2>4. 來源</h2>
        <label className="check">
          <input type="checkbox" checked={limitSources} onChange={(e) => setLimitSources(e.target.checked)} /> 只使用勾選的來源（預設：每個欄位依自己的順位使用全部來源）
        </label>
        {limitSources && (
          <div className="chips-row">
            {Object.entries(sources).map(([k, s]) => (
              <label key={k} className="check">
                <input
                  type="checkbox"
                  checked={picked.has(k)}
                  onChange={(e) => {
                    const n = new Set(picked);
                    if (e.target.checked) n.add(k);
                    else n.delete(k);
                    setPicked(n);
                  }}
                />
                {s.name}
              </label>
            ))}
          </div>
        )}
      </section>
      <section className="form-section">
        <h2>5. 模式</h2>
        <div className="modes">
          {Object.entries(meta.modes).map(([k, v]) => (
            <label key={k} className={`mode ${mode === k ? "on" : ""}`}>
              <input type="radio" name="mode" value={k} checked={mode === k} onChange={() => setMode(k)} />
              <strong>{v}</strong>
              <small>{MODE_HELP[k]}</small>
            </label>
          ))}
        </div>
      </section>
      <section className="form-section">
        <h2>預估</h2>
        {!hasWords ? (
          <p className="muted">選擇字表或輸入單字後顯示預估。</p>
        ) : estErr ? (
          <ErrorBox error={estErr} />
        ) : !est ? (
          <Loading what="計算預估" />
        ) : (
          <>
            <p>
              {est.words} 個單字 × {est.fields} 個欄位
            </p>
            <div className="grid2">
              {(["target", "native"] as const).map((k) => (
                <div key={k} className="card">
                  <h3>{k === "target" ? `目標語言資料（${langName(target)}）` : `母語資料（${langName(native)}）`}</h3>
                  <dl className="kv">
                    <dt>目前完整率</dt><dd><Rate value={est[k].current_completeness} /></dd>
                    <dt>預估完整率</dt><dd><Rate value={est[k].expected_completeness} /></dd>
                    <dt>要處理</dt><dd>{est[k].to_process} 格（已完成 {est[k].already_complete}）</dd>
                    <dt>請求數上限</dt><dd>{est[k].requests_upper_bound.toLocaleString()}</dd>
                    <dt>預估儲存量</dt><dd>{fmtBytes(est[k].storage_bytes)}</dd>
                  </dl>
                </div>
              ))}
              <div className="card">
                <h3>音檔</h3>
                <dl className="kv">
                  <dt>檔案</dt><dd>最多 {est.audio.files} 個</dd>
                  <dt>請求數上限</dt><dd>{est.audio.requests_upper_bound.toLocaleString()}</dd>
                  <dt>預估儲存量</dt><dd>{fmtBytes(est.audio.storage_bytes)}</dd>
                </dl>
              </div>
              <div className="card">
                <h3>詞義圖片</h3>
                <dl className="kv">
                  <dt>圖片</dt><dd>最多 {est.images.files} 張（名詞前兩個詞義）</dd>
                  <dt>請求數上限</dt><dd>{est.images.requests_upper_bound.toLocaleString()}</dd>
                  <dt>預估儲存量</dt><dd>{fmtBytes(est.images.storage_bytes)}</dd>
                  <dt>AI 標籤</dt><dd>約 {Math.ceil(est.images.ai_label_seconds / 60)} 分鐘（背景處理）</dd>
                </dl>
              </div>
            </div>
            <p className="hint">{est.note}</p>
          </>
        )}
      </section>
      {err && <ErrorBox error={err} />}
      <div className="actions sticky-actions">
        <button className="btn btn-primary" disabled={busy || !hasWords || !fields.size} onClick={start}>
          {busy ? "建立中…" : `開始${meta.modes[mode]}工作`}
        </button>
        <span className="muted">
          {langName(target)} → {langName(native)}
        </span>
      </div>
    </div>
  );
}
