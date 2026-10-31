import test from "node:test";
import assert from "node:assert/strict";
import { headline, hereKey, liveItems, minutesSince, type FlowRow } from "./flowLogic.ts";

const cell = (state: string, here = false) => ({ state, note: "", ...(here ? { here } : {}) });
const row = (key: string, wait: string, here: string | null, since: string | null = null): FlowRow => ({
  key, title: key, wait, status_text: "開發中", since,
  flow: { here, cells: { dev: { ...cell(here === "dev" ? "current" : "done", here === "dev"), note: "寫測試" },
                          ipad_verify: cell(here === "ipad_verify" ? "current" : "todo", here === "ipad_verify") } },
});

test("hereKey finds the marked gate", () => {
  assert.equal(hereKey(row("a", "mac", "ipad_verify")), "ipad_verify");
  assert.equal(hereKey(row("b", "none", null)), null);
});

test("headline counts waiting-for-you and the gates", () => {
  const h = headline([row("a", "you", "dev"), row("b", "ai", "dev"), row("c", "mac", "ipad_verify")]);
  assert.match(h, /3 項：1 項等你，1 項還在開發，1 項在驗證，0 項可發布/);
});

test("live items flag 30 minutes without news as stale", () => {
  const now = Date.parse("2026-11-01T12:00:00Z");
  const live = liveItems([row("a", "ai", "dev", "2026-11-01T11:50:00Z"), row("b", "ai", "dev", "2026-11-01T11:00:00Z"), row("c", "mac", "dev")], now);
  assert.deepEqual(live.map((x) => [x.key, x.minutes, x.stale, x.doing]), [["a", 10, false, "寫測試"], ["b", 60, true, "寫測試"]]);
  assert.equal(minutesSince(null), null);
});
