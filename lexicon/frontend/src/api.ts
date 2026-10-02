// Thin client for the FastAPI service. In development the Vite proxy adds
// X-API-Key; when the built UI is served by the API itself (/ui/), the
// key is asked for once and kept in sessionStorage for this tab only.

const KEY_STORE = "lexicon.apiKey";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function storedKey(): string | null {
  try {
    return sessionStorage.getItem(KEY_STORE);
  } catch {
    return null;
  }
}

export function setApiKey(key: string) {
  try {
    sessionStorage.setItem(KEY_STORE, key);
  } catch {
    /* private mode: the key lasts until reload */
  }
  memoryKey = key;
}

let memoryKey: string | null = null;
let keyListeners: Array<() => void> = [];
export function onKeyNeeded(fn: () => void) {
  keyListeners.push(fn);
  return () => {
    keyListeners = keyListeners.filter((f) => f !== fn);
  };
}

// The API restarts now and then (new code, a worker update); the Vite proxy
// answers 502 meanwhile. Reads are retried a few times before a clear
// message is shown (問題回報 #55).
const RETRY_STATUS = new Set([502, 503, 504]);
const RETRY_WAIT_MS = [500, 1500, 3000];
export const UNREACHABLE = "後台 API 暫時連不上（可能正在重新啟動），已自動重試；請稍候再按「重新整理」。";

async function send(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<Response> {
  const key = memoryKey ?? storedKey();
  return fetch(`/api${path}`, {
    method,
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(key ? { "X-API-Key": key } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

async function request<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  let res: Response | null = null;
  for (let attempt = 0; ; attempt++) {
    try {
      res = await send(method, path, body, headers);
    } catch {
      res = null; // the connection itself failed
    }
    const transient = res === null || RETRY_STATUS.has(res.status);
    if (!transient || method !== "GET" || attempt >= RETRY_WAIT_MS.length) break;
    await new Promise((r) => setTimeout(r, RETRY_WAIT_MS[attempt]));
  }
  if (res === null || RETRY_STATUS.has(res.status)) throw new ApiError(res?.status ?? 0, UNREACHABLE);
  if (res.status === 401) keyListeners.forEach((f) => f());
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  const type = res.headers.get("content-type") || "";
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) =>
    request<T>("POST", path, body ?? {}, headers),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  async download(path: string, filename: string) {
    const key = memoryKey ?? storedKey();
    const res = await fetch(`/api${path}`, { headers: key ? { "X-API-Key": key } : {} });
    if (!res.ok) throw new ApiError(res.status, `下載失敗（${res.status}）`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  },
};

export function newIdempotencyKey() {
  return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

// ── Types ───────────────────────────────────────────────────────────

export type Lang = { code: string; name: string; native_name: string; zh: string };
export type FieldMeta = {
  key: string;
  label: string;
  block: string;
  scope: "target" | "native";
  languages: string[] | null;
  description: string;
};
export type Meta = {
  languages: Lang[];
  pairs: { target_language: string; native_language: string }[];
  blocks: { key: string; label: string }[];
  fields: FieldMeta[];
  strategies: Record<string, string>;
  modes: Record<string, string>;
};

export type Step = {
  source: string;
  name?: string;
  kind?: string;
  position?: number;
  enabled: boolean;
  timeout_s: number;
  retries: number;
  min_confidence: number;
  max_results: number | null;
  continue_on_failure: boolean;
  implemented?: boolean;
  license?: string;
};
export type SourceOption = {
  source: string;
  name: string;
  kind: string;
  license: string;
  implemented: boolean;
  note: string;
  reason?: string;
};
export type Policy = {
  target_language: string;
  native_language: string;
  field: string;
  label: string;
  block: string;
  scope: string;
  description: string;
  strategy: string | null;
  max_items: number | null;
  version: number;
  steps: Step[];
  available: SourceOption[];
  unsupported: SourceOption[];
  status: string;
  first_source: string | null;
  backups: number;
  last_test: LastTest | null;
  default: { sources: string[]; strategy: string; max_items: number | null };
};
export type LastTest = {
  word: string;
  at: string;
  status: string;
  adopted: number;
  errors: number;
  draft?: boolean;
};
export type FieldRow = {
  field: string;
  label: string;
  scope: string;
  status: string;
  strategy: string | null;
  max_items: number | null;
  first_source: string | null;
  first_source_name: string | null;
  backups: number;
  sources: string[];
  version: number;
  last_test: LastTest | null;
};
export type Overview = {
  target_language: string;
  native_language: string;
  strategies: Record<string, string>;
  blocks: {
    block: string;
    label: string;
    fields: FieldRow[];
    counts: { total: number; configured: number; unset: number; attention: number; errors: number };
  }[];
};
export type TestCandidate = {
  value: Record<string, unknown>;
  key: string;
  slot: string;
  source: string;
  confidence: number;
  language: string;
  valid: boolean;
  invalid_reason: string | null;
  adopted: boolean;
};
export type TestResult = {
  word: string;
  lemma: string;
  field: string;
  status: string;
  strategy: string | null;
  items: Record<string, unknown>[];
  missing: string[];
  draft: boolean;
  pairs: { n: number; slot: string; target: string; native: string | null; source: string | null; ai: boolean }[];
  dependencies: { field: string; label: string; from: string; count: number; status?: string }[];
  steps: {
    source: string;
    name: string;
    position: number;
    status: string;
    reason: string;
    ms: number;
    valid_count: number;
    adopted: number;
    error_kind: string | null;
    raw: unknown;
    candidates: TestCandidate[];
  }[];
};

export type Job = {
  id: number;
  target_language: string;
  native_language: string;
  mode: string;
  mode_label: string;
  status: string;
  total: number;
  checkpoint: number;
  progress: number;
  counts: Record<string, number>;
  fields: number;
  sources: string[] | null;
  worker_id: string | null;
  retry_of: number | null;
  note: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  heartbeat_at: string | null;
  succeeded: number;
  partial: number;
  missing: number;
  failed: number;
  skipped: number;
  unset: number;
  word_preview: string[];
  word_preview_remaining: number;
  current_word: string | null;
};
export type JobDetail = Job & {
  words: string[];
  field_list: string[];
  steps: {
    field: string;
    label: string;
    source: string;
    position: number;
    succeeded: number;
    missing: number;
    failed: number;
    skipped: number;
    retried: number;
    avg_ms: number;
  }[];
  errors_by_type: { error_type: string; source: string; count: number }[];
  errors: {
    id: number;
    lemma: string;
    field: string;
    source: string;
    error_type: string;
    message: string;
    attempts: number;
    next_retry_at: string | null;
    created_at: string;
  }[];
  logs: { id: number; level: string; message: string; at: string }[];
};
