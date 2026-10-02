import { useCallback, useEffect, useMemo, useState } from "react";
import { api, onKeyNeeded, setApiKey, type Meta } from "./api";
import { AppCtx, ErrorBox, Loading, Modal } from "./ui";
import Dashboard from "./pages/Dashboard";
import Policies from "./pages/Policies";
import StartImport from "./pages/StartImport";
import Jobs from "./pages/Jobs";
import JobDetail from "./pages/JobDetail";
import Coverage from "./pages/Coverage";
import Word from "./pages/Word";
import Snapshots from "./pages/Snapshots";
import Export from "./pages/Export";
import CardWorkspace from "./pages/CardWorkspace";
import Images from "./pages/Images";
import Issues from "./pages/Issues";

const NAV = [
  ["/", "總覽", "Dashboard"],
  ["/issues", "問題回報", "Issue Reports"],
  ["/policies", "來源順位", "Source Policies"],
  ["/imports/new", "開始擷取", "Start Import Job"],
  ["/jobs", "工作佇列", "Jobs"],
  ["/coverage", "單字覆蓋率", "Word Coverage"],
  ["/card-data", "字卡資料檢查", "Card Data"],
  ["/card-studio", "字卡工作室", "Card Studio"],
  ["/images", "圖片庫", "Image Library"],
  ["/snapshots", "來源快照", "Source Snapshots"],
  ["/export", "匯出給 Flutter", "Export for Flutter"],
] as const;

function useHashRoute() {
  const read = () => window.location.hash.replace(/^#/, "") || "/";
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const f = () => setRoute(read());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return route;
}

const PAIR_STORE = "lexicon.pair";

function loadPair(): [string, string] {
  try {
    const v = JSON.parse(localStorage.getItem(PAIR_STORE) || "null");
    if (Array.isArray(v) && v.length === 2) return v as [string, string];
  } catch {
    /* ignore */
  }
  return ["en", "zh-TW"];
}

export default function App() {
  const route = useHashRoute();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [sources, setSources] = useState<Record<string, { name: string; kind: string; implemented: boolean; license: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const [[target, native], setPairState] = useState<[string, string]>(loadPair);
  const [askKey, setAskKey] = useState(false);
  const [keyInput, setKeyInput] = useState("");

  const load = useCallback(async () => {
    try {
      setError(null);
      const [m, src] = await Promise.all([
        api.get<Meta>("/meta"),
        api.get<{ key: string; name: string; kind: string; implemented: boolean; license: string }[]>("/sources"),
      ]);
      setMeta(m);
      setSources(Object.fromEntries(src.map((s) => [s.key, s])));
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
    return onKeyNeeded(() => setAskKey(true));
  }, [load]);

  const setPair = useCallback((t: string, n: string) => {
    setPairState([t, n]);
    try {
      localStorage.setItem(PAIR_STORE, JSON.stringify([t, n]));
    } catch {
      /* ignore */
    }
  }, []);

  const ctx = useMemo(() => {
    if (!meta) return null;
    const langs = Object.fromEntries(meta.languages.map((l) => [l.code, l.zh]));
    const fields = Object.fromEntries(meta.fields.map((f) => [f.key, f.label]));
    return {
      meta,
      target,
      native,
      setPair,
      sources,
      langName: (c: string) => langs[c] ?? c,
      fieldLabel: (k: string) => fields[k] ?? k,
      sourceName: (k: string) => sources[k]?.name ?? k,
    };
  }, [meta, target, native, setPair, sources]);

  let page;
  const m = route.match(/^\/jobs\/(\d+)$/);
  const w = route.match(/^\/words\/([^/]+)\/([^/]+)\/(.+)$/);
  if (route === "/") page = <Dashboard />;
  else if (route.startsWith("/policies")) page = <Policies route={route} />;
  else if (route === "/imports/new") page = <StartImport />;
  else if (route === "/jobs") page = <Jobs />;
  else if (m) page = <JobDetail id={Number(m[1])} />;
  else if (route.startsWith("/coverage")) page = <Coverage />;
  else if (w) page = <Word target={w[1]} native={w[2]} lemma={decodeURIComponent(w[3])} />;
  // Recordings are on each word's page (單字覆蓋率 → 單字).
  else if (route === "/audio") page = <Coverage />;
  else if (route === "/images") page = <Images />;
  else if (route === "/issues") page = <Issues />;
  else if (route === "/snapshots") page = <Snapshots />;
  else if (route === "/export") page = <Export />;
  else page = <div className="page"><h1>找不到頁面</h1></div>;

  const active = NAV.filter(([p]) => (p === "/" ? route === "/" : route.startsWith(p) || (p === "/jobs" && route.startsWith("/jobs")) || (p === "/coverage" && route.startsWith("/words")))).map(([p]) => p);

  return (
    <div className="shell">
      <nav className="side" aria-label="主選單">
        <div className="brand">
          <strong>語言資料後台</strong>
          <span>來源管理與擷取</span>
        </div>
        {NAV.map(([p, zh, en]) => (
          <a key={p} href={`#${p}`} className={active.includes(p) ? "active" : ""} aria-current={active.includes(p) ? "page" : undefined}>
            <span>{zh}</span>
            <small>{en}</small>
          </a>
        ))}
        <div className="side-foot">API 127.0.0.1:8770 · PostgreSQL</div>
      </nav>
      <main className="main">
        {route.startsWith('/card-data') || route.startsWith('/card-studio') ? (
          <CardWorkspace route={route} target={target} native={native} />
        ) : error && !meta ? (
          <div className="page">
            <ErrorBox error={`連不上 API：${error}`} onRetry={load} />
            <p className="muted">請確認 API（python -m uvicorn app.main:app --app-dir backend --port 8770）與 PostgreSQL 都已啟動。</p>
          </div>
        ) : !ctx ? (
          <Loading what="連線到 API" />
        ) : (
          <AppCtx.Provider value={ctx}>{page}</AppCtx.Provider>
        )}
      </main>
      {askKey && (
        <Modal
          title="需要 API 金鑰"
          onClose={() => setAskKey(false)}
          footer={
            <button
              className="btn btn-primary"
              disabled={!keyInput}
              onClick={() => {
                setApiKey(keyInput);
                setAskKey(false);
                load();
              }}
            >
              使用這個金鑰
            </button>
          }
        >
          <p>API 拒絕了請求（401）。請貼上 lexicon/.env 裡的 LEXICON_API_KEY；它只保存在這個分頁。</p>
          <input type="password" className="input" value={keyInput} onChange={(e) => setKeyInput(e.target.value)} autoFocus aria-label="API 金鑰" />
        </Modal>
      )}
    </div>
  );
}
