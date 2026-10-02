import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, type Meta } from "./api";

// ── App-wide context: metadata and the chosen language direction ─────

type Ctx = {
  meta: Meta;
  target: string;
  native: string;
  setPair: (target: string, native: string) => void;
  langName: (code: string) => string;
  fieldLabel: (key: string) => string;
  sourceName: (key: string) => string;
  sources: Record<string, { name: string; kind: string; implemented: boolean; license: string }>;
};
export const AppCtx = createContext<Ctx | null>(null);
export function useApp() {
  const c = useContext(AppCtx);
  if (!c) throw new Error("AppCtx missing");
  return c;
}

// ── Data loading ────────────────────────────────────────────────────

export function useLoad<T>(path: string | null, deps: unknown[] = [], pollMs?: number) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const load = useCallback(
    async (quiet = false) => {
      if (!path) return;
      const n = ++seq.current;
      if (!quiet) setLoading(true);
      try {
        const d = await api.get<T>(path);
        if (n === seq.current) {
          setData(d);
          setError(null);
        }
      } catch (e) {
        if (n === seq.current) setError((e as Error).message);
      } finally {
        if (n === seq.current) setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [path, ...deps],
  );
  useEffect(() => {
    setData(null);
    load();
  }, [load]);
  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(() => load(true), pollMs);
    return () => clearInterval(t);
  }, [load, pollMs]);
  return { data, error, loading, reload: load, setData };
}

// ── Small components ────────────────────────────────────────────────

const STATUS: Record<string, [string, string]> = {
  complete: ["完成", "ok"],
  user_override: ["使用者覆寫", "info"],
  none: ["查無（這個字沒有）", "ok"],
  not_applicable: ["不適用", "muted"],
  partial: ["部分缺少", "warn"],
  short: ["缺漏（來源已查遍）", "bad"],
  missing: ["缺值", "warn"],
  failed: ["失敗", "bad"],
  unset: ["未設定", "bad"],
  unavailable: ["來源未實作", "muted"],
  skipped: ["已是最新", "muted"],
  not_run: ["尚未擷取", "muted"],
  ok: ["已設定", "ok"],
  attention: ["需注意", "warn"],
  error: ["測試有錯誤", "bad"],
  succeeded: ["成功", "ok"],
  queued: ["排隊中", "muted"],
  running: ["執行中", "info"],
  pausing: ["暫停中…", "warn"],
  paused: ["已暫停", "warn"],
  cancelling: ["取消中…", "warn"],
  cancelled: ["已取消", "muted"],
  completed: ["完成", "ok"],
  completed_with_errors: ["完成（有錯誤）", "warn"],
  ready: ["就緒", "ok"],
  building: ["建立中", "info"],
  downloading: ["下載中", "info"],
  pending: ["等待", "muted"],
  retrying: ["重試中", "warn"],
};

export type ScoredTag = { word: string; pos?: string | null; score?: number | null };

/** "99%": a label's recognition score — how sure the vision model is that the
 *  picture shows it (its probability of answering "shown" when it checks the
 *  label again). Labels pass at 80%. */
export const scoreText = (s?: number | null) => (s == null ? "未評分" : `${Math.round(s * 100)}%`);

/** The AI labels of a picture with their recognition scores, best first. */
export function TagScores({ tags, word, label = "AI 標籤與辨識分數" }: { tags?: ScoredTag[] | null; word: string; label?: string }) {
  if (!tags?.length) return null;
  const tone = (s: number) => (s >= 0.8 ? "ok" : s >= 0.5 ? "warn" : "bad");
  return <ul className="tag-scores" aria-label={label}>
    {[...tags].sort((a, b) => (b.score ?? -1) - (a.score ?? -1)).map((t) => (
      <li key={t.word} className={`chip chip-${t.score == null ? "muted" : tone(t.score)}`}
          style={t.word.toLowerCase() === word ? { fontWeight: 700 } : undefined}>
        {t.word}{t.pos ? <small> {t.pos}</small> : null} {scoreText(t.score)}
      </li>
    ))}
  </ul>;
}

export function Chip({ status, label }: { status: string; label?: string }) {
  const [text, tone] = STATUS[status] ?? [status, "muted"];
  return <span className={`chip chip-${tone}`}>{label ?? text}</span>;
}

export function Loading({ what = "載入中" }: { what?: string }) {
  return (
    <div className="state" role="status">
      <span className="spinner" aria-hidden /> {what}…
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <strong>發生錯誤：</strong>
      {error}
      {onRetry && (
        <button className="btn btn-small" onClick={onRetry}>
          重試
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state state-empty">{children}</div>;
}

export function Progress({ value, tone }: { value: number; tone?: string }) {
  const pct = Math.max(0, Math.min(100, value * 100));
  return (
    <div className={`progress ${tone ? `progress-${tone}` : ""}`} role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Rate({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="muted">—</span>;
  const tone = value >= 0.9 ? "ok" : value >= 0.6 ? "warn" : "bad";
  return (
    <span className="rate">
      <Progress value={value} tone={tone} />
      <span>{Math.round(value * 100)}%</span>
    </span>
  );
}

export function Modal({ title, onClose, children, footer }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <header>
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="關閉">
            ×
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer>{footer}</footer>}
      </div>
    </div>
  );
}

export function useToast() {
  const [msg, setMsg] = useState<{ text: string; tone: string } | null>(null);
  useEffect(() => {
    if (!msg) return;
    const t = setTimeout(() => setMsg(null), 3500);
    return () => clearTimeout(t);
  }, [msg]);
  const node = msg ? (
    <div className={`toast toast-${msg.tone}`} role="status">
      {msg.text}
    </div>
  ) : null;
  return { toast: (text: string, tone = "ok") => setMsg({ text, tone }), node };
}

export function PairPicker({ compact }: { compact?: boolean }) {
  const { meta, target, native, setPair } = useApp();
  return (
    <div className={`pair ${compact ? "pair-compact" : ""}`}>
      <label>
        <span>目標語言</span>
        <select value={target} onChange={(e) => {
          const t = e.target.value;
          setPair(t, native === t ? meta.languages.find((l) => l.code !== t)!.code : native);
        }}>
          {meta.languages.map((l) => (
            <option key={l.code} value={l.code}>
              {l.zh}
            </option>
          ))}
        </select>
      </label>
      <span className="arrow" aria-hidden>
        →
      </span>
      <label>
        <span>母語</span>
        <select value={native} onChange={(e) => setPair(target, e.target.value)}>
          {meta.languages
            .filter((l) => l.code !== target)
            .map((l) => (
              <option key={l.code} value={l.code}>
                {l.zh}
              </option>
            ))}
        </select>
      </label>
    </div>
  );
}

// ── Value formatting ────────────────────────────────────────────────

export function summarize(v: Record<string, unknown> | null | undefined): string {
  if (!v) return "";
  const s = (k: string) => (v[k] === undefined || v[k] === null ? "" : String(v[k]));
  if (v.tts) return `系統 TTS（${s("locale")}）`;
  if (v.gloss) return `${v.pos ? `[${s("pos")}] ` : ""}${s("gloss")}`;
  if (v.url) return `${decodeURIComponent(s("url").split("/").pop() || "")}${Array.isArray(v.accent) && v.accent.length ? `（${(v.accent as string[]).join("、")}）` : ""}`;
  if (v.ipa) return `${s("ipa")}${Array.isArray(v.accent) && v.accent.length ? `（${(v.accent as string[]).join("、")}）` : ""}`;
  if (v.phonemes) return s("phonemes");
  if (v.syllables) return (v.syllables as string[]).join("·");
  if (v.word && v.text) return `${s("word")}：${s("text")}`;
  if (v.word) return [s("word"), v.pos ? `(${s("pos")})` : "", v.difference ? `〔${s("difference")}〕` : "", v.label ? `〔${s("affix")} ${s("label")}〕` : ""].filter(Boolean).join(" ");
  if (v.form) return s("form");
  if (v.morpheme) return s("morpheme");
  if (v.language && !v.text) return s("language");
  if (v.text) return s("text");
  if (v.level) return s("level");
  if (v.zipf !== undefined) return `Zipf ${s("zipf")}`;
  if (v.label) return s("label");
  if (v.accent) return s("accent");
  if (v.count) return `${s("count")} 音節`;
  if (v.pattern) return `重音 ${s("pattern")}`;
  if (v.primary_syllable) return `第 ${s("primary_syllable")} 音節重音`;
  if (v.pos) return s("pos");
  if (v.sense_key && v.example_key) return `例句 ${s("example_key")} → 詞義 ${s("sense_key")}`;
  return JSON.stringify(v);
}

export function fmtTime(t: string | null | undefined) {
  if (!t) return "—";
  const d = new Date(t);
  return d.toLocaleString("zh-TW", { hour12: false, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function fmtBytes(n: number | null | undefined) {
  if (n === null || n === undefined) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function Link({ to, children, className }: { to: string; children: ReactNode; className?: string }) {
  return (
    <a href={`#${to}`} className={className}>
      {children}
    </a>
  );
}
