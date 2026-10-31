// 流程表 (card #928): the pure parts of the 全部項目 table, kept apart so node --test can run them.
export type Cell = { state: string; note: string; here?: boolean };
export type FlowRow = {
  key: string; title: string; wait: string; status_text: string; since: string | null;
  flow?: { cells: Record<string, Cell>; here: string | null };
};

export const STALE_MIN = 30;
export const CELL_LABEL: Record<string, string> = { done: "通過", current: "進行中", failed: "不通過", todo: "等待", skipped: "略過" };

export function minutesSince(iso: string | null, now = Date.now()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : Math.max(0, Math.round((now - t) / 60000));
}

/** 現在進行中: the items an AI is working on right now, with how long since they last moved. */
export function liveItems(rows: FlowRow[], now = Date.now()) {
  return rows.filter((r) => r.wait === "ai").map((r) => {
    const min = minutesSince(r.since, now);
    const dev = r.flow?.cells.dev;
    return { key: r.key, title: r.title, doing: (dev && dev.note) || r.status_text, minutes: min, stale: min !== null && min > STALE_MIN };
  });
}

/** 頁首一句話: how many wait for the owner and how many are still at the earlier gates. */
export function headline(rows: FlowRow[]): string {
  const you = rows.filter((r) => r.wait === "you").length;
  const at = (...ks: string[]) => rows.filter((r) => r.wait !== "you" && r.flow?.here && ks.includes(r.flow.here)).length;
  const front = at("dev"), verify = at("windows_check", "mac_verify", "ipad_verify"), ready = at("ready");
  return `${rows.length} 項：${you} 項等你，${front} 項還在開發，${verify} 項在驗證，${ready} 項可發布`;
}

/** The one cell marked 停在這裡 in a row (the first gate that has not passed). */
export function hereKey(r: FlowRow): string | null {
  const cells = r.flow?.cells ?? {};
  return Object.keys(cells).find((k) => cells[k].here) ?? null;
}
