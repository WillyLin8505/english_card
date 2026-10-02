import { useState } from "react";
import { api, newIdempotencyKey } from "../api";
import WordMedia, { type WordAudio, type WordImage } from "./WordMedia";
import { Chip, Empty, ErrorBox, Link, Loading, Modal, fmtTime, summarize, useApp, useLoad, useToast } from "../ui";

type Item = Record<string, unknown>;
type WordView = {
  lemma: string;
  display: string;
  target_language: string;
  native_language: string;
  lexemes: { id: number; pos: string; status: string; cefr: string | null; zipf: number | null }[];
  fields: {
    field: string;
    label: string;
    block: string;
    scope: string;
    status: string;
    items: Item[];
    missing: string[];
    override: boolean;
    resolved_at: string | null;
    lookups: { source: string; status: string; count: number; error: string | null; at: string }[];
  }[];
  senses: { n: number; sense_key: string; sense_id: number | null; pos: string; gloss: string; labels: string[]; source: string; native: Item | null; status: string }[];
  examples: { n: number; key: string; text: string; source: string; level: string | null; translation: Item | null; status: string }[];
  relations: Record<string, { label: string; items: { word: string; pos: string | null; source: string; note: string | null; difference: string | null; relation: Item | null; native: Item | null; lexeme_id: number | null; linked: string | null; status: string; zipf: number | null; rarity: string | null; cefr: string | null; cefr_source: string | null; hide_by_default: boolean }[] }>;
  morphemes: {
    summary: string;
    method: string;
    source: string;
    ai: boolean;
    parts: { part: string; kind: "prefix" | "root" | "suffix"; meaning: string | null; free: boolean; native: Item | null }[];
  } | null;
  issues: { field: string; target: string | null; message: string; kind: string }[];
  summary: { target: { complete: number; total: number }; native: { complete: number; total: number } };
  audio: WordAudio[];
  images: WordImage[];
  images_pending: number;
};

type FieldDetail = {
  field: string;
  label: string;
  status: string;
  items: Item[];
  override: { items: Item[]; note: string; updated_at: string } | null;
  provenance: { source: string; item_key: string; position: number; strategy: string; processed_at: string }[];
  candidates: { id: number; source: string; value: Item; confidence: number; valid: boolean; invalid_reason: string | null; license: string; attribution: string; source_record_id: string; retrieved_at: string; adopted: boolean }[];
};

export default function Word({ target, native, lemma }: { target: string; native: string; lemma: string }) {
  const { langName, meta, sourceName } = useApp();
  const w = useLoad<WordView>(`/words/${target}/${native}/${encodeURIComponent(lemma)}`, [target, native, lemma]);
  const [detail, setDetail] = useState<string | null>(null);
  const [busyField, setBusyField] = useState<string | null>(null);
  const { toast, node } = useToast();

  if (w.error) return <div className="page"><p><Link to="/coverage">← 覆蓋率</Link></p><ErrorBox error={w.error} /></div>;
  if (!w.data) return <Loading />;
  const d = w.data;
  const lexId = d.lexemes.find((l) => l.status === "full")?.id;

  const refresh = async (field: string) => {
    if (!lexId) return;
    setBusyField(field);
    try {
      const r = await api.post<{ status: string }>(`/words/${lexId}/fields/${field}/refresh`, { target_language: target, native_language: native, mode: "force_refresh" });
      toast(`已重抓：${r.status}`);
      w.reload(true);
    } catch (e) {
      toast((e as Error).message, "bad");
    } finally {
      setBusyField(null);
    }
  };

  const FieldList = ({ scope }: { scope: string }) => (
    <div className="field-status-list">
      {meta.blocks.map((b) => {
        const fs = d.fields.filter((f) => f.block === b.key && f.scope === scope);
        if (!fs.length) return null;
        return (
          <div key={b.key}>
            <h4>{b.label}</h4>
            <ul>
              {fs.map((f) => (
                <li key={f.field} className={`fs fs-${f.status}`}>
                  <span className="fs-label">{f.label}</span>
                  <Chip status={f.status} />
                  <span className="fs-value">
                    {f.items.slice(0, 3).map((it, i) => (
                      <span key={i} className="val">
                        {summarize(it)}
                        {Boolean(it.ai) && <span className="ai">AI</span>}
                      </span>
                    ))}
                    {f.items.length > 3 && <span className="muted">…共 {f.items.length}</span>}
                    {f.missing.length > 0 && <span className="warn"> 缺 {f.missing.length}</span>}
                  </span>
                  <span className="fs-actions">
                    <button className="btn btn-small" onClick={() => setDetail(f.field)}>來源紀錄</button>
                    {f.status !== "complete" && f.status !== "user_override" && f.status !== "unset" && lexId && (
                      <button className="btn btn-small" disabled={busyField === f.field} onClick={() => refresh(f.field)}>
                        {busyField === f.field ? "重抓中…" : "重抓"}
                      </button>
                    )}
                    {f.status === "unset" && <Link to={`/policies?field=${f.field}`}>設定來源</Link>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="page page-wide">
      {node}
      <header className="page-head">
        <div>
          <p><Link to="/coverage">← 覆蓋率</Link></p>
          <h1>{d.display}</h1>
          <p className="muted">
            {langName(target)} → {langName(native)} ·{" "}
            {d.lexemes.map((l) => (
              <span key={l.id} className="pill">
                #{l.id} {l.pos}{l.cefr ? ` · ${l.cefr}` : ""}{l.status === "stub" ? " · 連結用詞條" : ""}
              </span>
            ))}
          </p>
        </div>
        <div>
          <dl className="kv kv-inline">
            <dt>{langName(target)} 欄位</dt><dd>{d.summary.target.complete}/{d.summary.target.total}</dd>
            <dt>{langName(native)} 欄位</dt><dd>{d.summary.native.complete}/{d.summary.native.total}</dd>
          </dl>
          <RefetchWord target={target} native={native} word={d.display} />
        </div>
      </header>

      <WordMedia lemma={d.lemma} display={d.display} audio={d.audio ?? []} images={d.images ?? []}
                 imagesPending={d.images_pending ?? 0} onChanged={() => w.reload(true)}
                 audioGaps={(d.issues ?? []).filter((i: { field: string }) => i.field === "audio")} />

      {d.issues.length > 0 && (
        <section className="issues">
          <h2>待補項目（{d.issues.length}）</h2>
          <ul>
            {d.issues.slice(0, 60).map((i, k) => (
              <li key={k} className={i.kind === "failed" ? "bad" : "warn"}>
                {i.message}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2>構詞拆解</h2>
        {!d.morphemes ? (
          <Empty>還沒有拆解（「構詞拆解」欄位尚未擷取）。</Empty>
        ) : (
          <div className="morphemes">
            <div className="morph-parts" aria-label={d.morphemes.summary}>
              {d.morphemes.parts.map((p, i) => (
                <span key={i} className="morph-wrap">
                  {i > 0 && <span className="morph-plus" aria-hidden>+</span>}
                  <span className={`morph morph-${p.kind}`}>
                    <strong>{p.part}</strong>
                    <small className="morph-kind">{{ prefix: "字首", root: p.free ? "單字" : "字根", suffix: "字尾" }[p.kind]}</small>
                    {p.native ? (
                      <span className="morph-native">
                        {String(p.native.text)}
                        {Boolean(p.native.ai) && <span className="ai">AI</span>}
                      </span>
                    ) : d.morphemes!.parts.length > 1 ? (
                      <span className="bad morph-native">缺{langName(native)}意思</span>
                    ) : null}
                    {p.meaning && <span className="morph-en">{p.meaning}</span>}
                  </span>
                </span>
              ))}
            </div>
            <p className="muted">
              {d.morphemes.parts.length === 1 ? "單一字根，不再拆分。" : `${d.morphemes.parts.length} 個部分。`}
              來源：{sourceName(d.morphemes.source)}
              {d.morphemes.ai && <span className="ai">AI</span>}
              {d.morphemes.method === "wiktionary" && "（依 Wiktionary 的構詞標記）"}
            </p>
          </div>
        )}
      </section>

      <section>
        <h2>逐義釋義</h2>
        {d.senses.length === 0 ? (
          <Empty>沒有詞義。</Empty>
        ) : (
          <table className="table bilingual">
            <thead><tr><th>#</th><th>{langName(target)}（{d.senses[0] ? "釋義" : ""}）</th><th>{langName(native)}</th></tr></thead>
            <tbody>
              {d.senses.map((s) => (
                <tr key={s.sense_key}>
                  <td>{s.n}</td>
                  <td><span className="pos">{s.pos}</span> {s.gloss} <span className="src">{sourceName(s.source)}</span></td>
                  <td>{s.native ? <>{String(s.native.text)} <span className="src">{String(s.native.source)}</span>{Boolean(s.native.ai) && <span className="ai">AI</span>}</> : <span className="bad">缺{langName(native)}釋義</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section>
        <h2>例句</h2>
        {d.examples.length === 0 ? (
          <Empty>沒有例句。</Empty>
        ) : (
          <>
          <p className="muted">
            A1–C2 每級目標 3–5 句，優先採用有{langName(native)}翻譯的句子。{" "}
            {(["A1", "A2", "B1", "B2", "C1", "C2"] as const).map((level) =>
              `${level} ${d.examples.filter((e) => e.level === level).length}`).join(" · ")}
          </p>
          <table className="table bilingual">
            <thead><tr><th>#</th><th>{langName(target)}</th><th>{langName(native)}</th><th>難度</th></tr></thead>
            <tbody>
              {d.examples.map((e) => (
                <tr key={e.key}>
                  <td>{e.n}</td>
                  <td>{e.text} <span className="src">{sourceName(e.source)}</span></td>
                  <td>{e.translation ? <>{String(e.translation.text)} <span className="src">{String(e.translation.source)}</span>{Boolean(e.translation.ai) && <span className="ai">AI</span>}{Boolean(e.translation.converted) && <span className="pill">簡→繁</span>}</> : <span className="bad">例句 #{e.n} 缺翻譯</span>}</td>
                  <td>{e.level ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </>
        )}
      </section>

      <section>
        <h2>衍生詞與詞彙關係</h2>
        {Object.keys(d.relations).length === 0 ? (
          <Empty>沒有關係詞。</Empty>
        ) : (
          <div className="relations">
            {Object.entries(d.relations).map(([rel, r]) => (
              <div key={rel} className="card">
                <h3>{r.label}</h3>
                <ul>
                  {r.items.map((it) => (
                    <li key={it.word}>
                      <strong>{it.lexeme_id && it.linked === "full" ? <Link to={`/words/${target}/${native}/${encodeURIComponent(it.word)}`}>{it.word}</Link> : it.word}</strong>
                      {it.pos && <span className="pos">{it.pos}</span>}
                      {it.cefr && <span className="pill">{it.cefr}</span>}
                      {it.rarity && <span className={it.hide_by_default ? "bad" : "muted"}> {
                        ({ common: "常見", everyday: "日常", less_common: "較少見", uncommon: "不常見", rare: "生僻", very_rare: "極生僻" } as Record<string, string>)[it.rarity] ?? it.rarity
                      }{it.zipf != null ? ` · Zipf ${it.zipf}` : ""}</span>}
                      {it.hide_by_default && <span className="pill">App 預設隱藏</span>}
                      {it.relation && <span className="muted"> {String(it.relation.affix ?? "")} {String(it.relation.label ?? "")}</span>}
                      {it.difference && <span className="muted"> 〔{it.difference}〕</span>}
                      {" — "}
                      {it.native ? <>{String(it.native.text)}{Boolean(it.native.ai) && <span className="ai">AI</span>}</> : <span className="bad">缺{langName(native)}詞義</span>}
                      <span className="src">{sourceName(it.source)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="grid2">
        <section>
          <h2>{langName(target)} 欄位</h2>
          <FieldList scope="target" />
        </section>
        <section>
          <h2>{langName(native)} 欄位</h2>
          <FieldList scope="native" />
        </section>
      </div>

      {detail && <FieldDetailModal target={target} native={native} lemma={d.lemma} field={detail} onClose={() => setDetail(null)} onChanged={() => w.reload(true)} />}
    </div>
  );
}

function FieldDetailModal({ target, native, lemma, field, onClose, onChanged }: { target: string; native: string; lemma: string; field: string; onClose: () => void; onChanged: () => void }) {
  const { sourceName } = useApp();
  const path = `/words/${target}/${native}/${encodeURIComponent(lemma)}/fields/${field}`;
  const fd = useLoad<FieldDetail>(path, [path]);
  const [edit, setEdit] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const saveOverride = async () => {
    try {
      setErr(null);
      const items = JSON.parse(edit || "[]");
      if (!Array.isArray(items)) throw new Error("請輸入 JSON 陣列");
      fd.setData(await api.put<FieldDetail>(`${path}/override`, { items, note: "手動修改" }));
      setEdit(null);
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  const removeOverride = async () => {
    try {
      fd.setData(await api.del<FieldDetail>(`${path}/override`));
      onChanged();
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <Modal title={fd.data ? `「${lemma}」${fd.data.label}：來源紀錄` : "來源紀錄"} onClose={onClose}>
      {fd.error && <ErrorBox error={fd.error} />}
      {err && <ErrorBox error={err} />}
      {!fd.data ? (
        <Loading />
      ) : (
        <>
          <p>
            <Chip status={fd.data.status} /> 採用 {fd.data.items.length} 筆
            {fd.data.override && <span className="pill">使用者覆寫（{fmtTime(fd.data.override.updated_at)}）自動擷取不會蓋掉</span>}
          </p>
          <div className="actions">
            {edit === null ? (
              <button className="btn btn-small" onClick={() => setEdit(JSON.stringify((fd.data!.override?.items ?? fd.data!.items).map(({ key: _k, slot: _s, confidence: _c, source: _src, ...v }) => v), null, 1))}>
                手動修改
              </button>
            ) : (
              <>
                <button className="btn btn-small btn-primary" onClick={saveOverride}>儲存覆寫</button>
                <button className="btn btn-small" onClick={() => setEdit(null)}>取消</button>
              </>
            )}
            {fd.data.override && <button className="btn btn-small btn-ghost" onClick={removeOverride}>移除覆寫（改回自動）</button>}
          </div>
          {edit !== null && <textarea className="input code" rows={10} value={edit} onChange={(e) => setEdit(e.target.value)} aria-label="覆寫值（JSON）" />}
          <h4>候選值（所有來源）</h4>
          {fd.data.candidates.length === 0 ? (
            <Empty>沒有候選值（來源沒有資料，或這個欄位沒查過）。</Empty>
          ) : (
            <table className="table compact">
              <thead><tr><th>來源</th><th>值</th><th>可信度</th><th>驗證</th><th>採用</th><th>紀錄 ID</th><th>取得時間</th></tr></thead>
              <tbody>
                {fd.data.candidates.map((c) => (
                  <tr key={c.id} className={c.valid ? "" : "invalid"}>
                    <td>{sourceName(c.source)}</td>
                    <td>{summarize(c.value)}</td>
                    <td>{c.confidence}</td>
                    <td>{c.valid ? "通過" : <span className="bad">{c.invalid_reason}</span>}</td>
                    <td>{c.adopted ? "✓" : ""}</td>
                    <td className="mono">{c.source_record_id}</td>
                    <td>{fmtTime(c.retrieved_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {fd.data.provenance.length > 0 && (
            <p className="muted">
              溯源：{fd.data.provenance.map((p, i) => <span key={i} className="pill">{sourceName(p.source)} · 順位 {p.position} · {p.strategy}</span>)}
            </p>
          )}
        </>
      )}
    </Modal>
  );
}

/** Fetch the whole word again as an import job (all fields, pictures
 *  included), then follow its progress on the job page. */
function RefetchWord({ target, native, word }: { target: string; native: string; word: string }) {
  const { meta } = useApp();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const start = async (mode: "force_refresh" | "fill_missing") => {
    setBusy(mode);
    setErr(null);
    try {
      const job = await api.post<{ id: number }>("/imports", {
        target_language: target,
        native_language: native,
        mode,
        words: [word],
        fields: meta.fields.filter((f) => !f.languages || f.languages.includes(target)).map((f) => f.key),
        sources: null,
        note: mode === "force_refresh" ? `重新抓取「${word}」` : `補齊「${word}」的缺值`,
      }, { "Idempotency-Key": newIdempotencyKey() });
      window.location.hash = `/jobs/${job.id}`;
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  };
  return (
    <div className="toolbar">
      <button className="btn btn-primary" disabled={!!busy} onClick={() => start("force_refresh")}
              title="不使用快取，所有欄位重新向每個來源查詢（約 1 分鐘）">
        {busy === "force_refresh" ? "建立中…" : "重新抓取這個字"}
      </button>
      <button className="btn" disabled={!!busy} onClick={() => start("fill_missing")}
              title="只處理還不完整、或來源順位改過的欄位">
        {busy === "fill_missing" ? "建立中…" : "只補缺的"}
      </button>
      {err && <ErrorBox error={err} />}
    </div>
  );
}
