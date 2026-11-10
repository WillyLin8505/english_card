"""Goals the system pursues by itself (owner 11/10: 「你自動去偵測還有什麼事情沒做，而不要每次都是我下指令」).

Goal fr_en = an English native learning French can use the App; the checklist is
lexicon/docs/goals/fr_en_usable.md. dispatch_tick runs `goal_check.py run` every tick; it measures only when due
(dispatch_config goals.fr_en.every_hours) and then, without any LLM:
  · opens a 「[目標 法文] <code> …」 issue for every failing data/album item that has no open issue
    (the issue swarm dispatches it); a closed issue whose item still fails gets its next round at once if the card
    moved the number (D8 52.6 → 56.8 %: work done in batches; ROUND_LIMIT rounds), else after a day, twice at most;
  · requeues goal-related or [owner] cards blocked for stuck_hours (once a day each, three times in all);
  · writes the score on the goal card (skip_tasks keeps CLIs off it); all items passing twice marks it done.

    python lexicon/tools/goal_check.py report          # measure and print, change nothing
    python lexicon/tools/goal_check.py run [--force]   # what dispatch_tick does
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "lexicon" / "tools"
STATE = ROOT / "lexicon" / "state" / "goal_fr_en.json"
CONFIG = TOOLS / "dispatch_config.json"
CAPS = TOOLS / "agent_capabilities.json"
BASIC = ROOT / "lexicon" / "backend" / "app" / "fr_cefr_reviewed.json"
API = "http://127.0.0.1:5173/api"
TAIPEI = timezone(timedelta(hours=8))
FR_WORDS = ("法文", "法語", "法语", "French", "英法")
OPEN = ("open", "in_progress", "needs_decision")
VERIFIED = {"ready", "released", "done", "cancelled"}
BASIC_TOPICS = {"法語基礎字", "基礎單字", "日常基礎", "進階單字"}
SIMULATION_CARD = 496
# owner 11/10 「先只在我的 iPad 用」: nothing blocks the goal on the owner's side for now
OWNER_ITEMS = ("暫時沒有（owner 11/10：先只在自己的 iPad 用；要給別人安裝時再辦付費 Apple Developer 帳號 #1540 第 0 項、"
               "Google Client ID #1525）")
SEED_ISSUES = {"D4": 1555, "A1": 1556, "A2": 1556, "A3": 1562, "A4": 1563}
# owner 11/10 「春夏秋冬、年月、上下左右、交通、吃飯、生活……生活情境、旅遊情境」: album topics, matched exactly
THEME_TOPICS = ("季節", "月份與星期", "時間", "方位", "交通", "用餐", "居家生活", "購物", "天氣", "家庭", "身體", "衣服",
                "數字", "顏色", "問候與禮貌")
SITUATION_TOPICS = ("在餐廳", "在咖啡館", "在旅館", "在車站與機場", "問路", "在市場與商店", "看醫生與藥局", "自我介紹")
REFILE_LIMIT = 2   # re-files of an item whose last card did not move its number
ROUND_LIMIT = 10   # further rounds of an item whose cards keep moving it (owner 11/10: don't stop halfway)
REQUEUE_LIMIT = 3

# code, name, target text, area, severity, what the issue asks for
ITEMS = {
    "D1": ("基礎字在詞庫", "表上的字 ≥ 99.5%", "data", "medium",
           "把表上還不在詞庫的字匯入（card350_import.py 的流程）；純變化形（aimez、monté…）不用收，列出來就好。"),
    "D2": ("英文翻譯", "詞條 100%", "data", "medium", "補英文翻譯。"),
    "D3": ("音標", "詞條 ≥ 99.5%", "data", "low", "補音標（Kaikki、Lexique）。"),
    "D4": ("A1／A2 音檔", "A1、A2 詞條 100%", "data", "medium",
           "補錄音：同拼法其他詞性有錄音就共用；沒有就照 #829 用 Azure 合成。"),
    "D5": ("例句與英譯", "詞條 ≥ 95%", "data", "low", "補例句與英譯（Tatoeba）；沒有來源的列出來。"),
    "D6": ("CEFR 程度", "詞條 100%", "data", "medium", "補 CEFR（tools/card335_fr_cefr.py）。"),
    "D7": ("名詞陰陽性", "名詞 100%", "data", "medium", "補名詞陰陽性（tools/card429_forms.py）。"),
    "D8": ("A1／A2 名詞配圖", "A1、A2 名詞 ≥ 70% 有核准圖片", "data", "medium",
           "A1／A2 名詞配圖：先用英文已核准的圖（serve_app.meaning_index），再抓圖＋Qwen 打標籤＋核准；"
           "圖庫真的沒有的照 #830 標不配圖並列出。"),
    "A1": ("主題相片冊", "≥ 6 本法文主題相片冊上架、每本 ≥ 20 個詞", "data", "medium", "做法文主題相片冊（見 #1556）。"),
    "A2": ("分級相片冊", "A1、A2、B1 各一本上架", "data", "medium", "做 A1／A2／B1 分級相片冊（見 #1556）。"),
    "A3": ("生活主題相片冊", f"{len(THEME_TOPICS)} 本（{'、'.join(THEME_TOPICS)}）各 ≥ 15 詞", "data", "medium",
           "做法文生活主題相片冊（見 #1562）。"),
    "A4": ("旅遊與生活情境相片冊", f"{len(SITUATION_TOPICS)} 本（{'、'.join(SITUATION_TOPICS)}）各 ≥ 15 詞", "data", "medium",
           "做法文情境相片冊（見 #1563）。"),
    "P1": ("法文高嚴重度問題", "沒有還開著的", "app", "high", None),
    "P2": ("法文卡過 iPad 驗證", "全部到 ready 以後", "app", "medium", None),
    "P3": ("法文學習者模擬 #496", "最近一輪（24 小時內）沒有新問題", "app", "medium", None),
    "S1": ("卡住的卡", "沒有排回三次還卡住的", "other", "medium", None),
    "M1": ("Mac 驗證有在跑", "有卡等 iPad 驗證時，Mac 24 小時內有回報", "other", "high", None),
}
FILED = ("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "A1", "A2", "A3", "A4")


def now_tw() -> datetime:
    return datetime.now(TAIPEI)


def parse_iso(s) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=TAIPEI)


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def http(method: str, path: str, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def is_french(title: str) -> bool:
    return any(k in title for k in FR_WORDS) or title.startswith("[目標 法文]")


def due(state: dict, now: datetime, every_hours: float) -> bool:
    last = parse_iso(state.get("last_run"))
    return last is None or now - last >= timedelta(hours=every_hours)


def new_issue_count(progress: str) -> int | None:
    """Card #496 writes 「無新問題」, 「新問題 0」 or 「新問題：2 …」; None when it says nothing about it."""
    p = progress or ""
    if re.search(r"無新問題|沒有新問題|新問題[：:\s]*(?:無|0(?!\d))", p):
        return 0
    m = re.search(r"新問題[：:\s]*(\d+)", p)
    return int(m.group(1)) if m else None


def basic_words() -> dict[str, str]:
    raw = load_json(BASIC, {})
    if isinstance(raw, dict) and "words" in raw:
        raw = raw["words"]
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            if k.startswith("_"):
                continue
            out[k] = v if isinstance(v, str) else str((v or {}).get("cefr") or (v or {}).get("level") or "")
    else:
        for x in raw:
            if isinstance(x, dict) and (x.get("word") or x.get("lemma")):
                out[x.get("word") or x.get("lemma")] = str(x.get("cefr") or x.get("level") or "")
            elif isinstance(x, (list, tuple)) and x:
                out[x[0]] = str(x[1]) if len(x) > 1 else ""
    return out


NO_PICTURE_FILES = ("card830_no_picture.json", "card1048_no_picture.json")


def no_picture_ids(state: Path | None = None) -> list[int]:
    """Lexeme ids marked "no_picture" (#951/#1566): abstract nouns that get no picture, so D8 leaves them out."""
    ids: set[int] = set()
    for name in NO_PICTURE_FILES:
        try:
            ids.update(int(i) for i in json.loads(((state or ROOT / "lexicon" / "state") / name).read_text(encoding="utf-8"))["lexemes"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return sorted(ids)


def measure_db(words: list[str]) -> dict:
    sys.path.insert(0, str(ROOT / "lexicon" / "backend"))
    from sqlalchemy import text  # noqa: PLC0415
    from app import db  # noqa: PLC0415

    L = "l.language='fr' AND l.status='full' AND l.lemma = ANY(:w)"
    has_audio = "EXISTS (SELECT 1 FROM pronunciations p WHERE p.lexeme_id=l.id AND p.audio_asset_id IS NOT NULL)"
    has_img = ("EXISTS (SELECT 1 FROM sense_images si JOIN senses s ON s.id=si.sense_id "
               "WHERE s.lexeme_id=l.id AND si.review_status='approved')")
    q = {
        "present": "SELECT count(DISTINCT lemma) FROM lexemes WHERE language='fr' AND lemma = ANY(:w)",
        "entries": f"SELECT count(*) FROM lexemes l WHERE {L}",
        "en": f"SELECT count(*) FROM lexemes l WHERE {L} AND EXISTS (SELECT 1 FROM senses s JOIN sense_translations t "
              f"ON t.sense_id=s.id AND t.native_language='en' WHERE s.lexeme_id=l.id)",
        "ipa": f"SELECT count(*) FROM lexemes l WHERE {L} AND EXISTS (SELECT 1 FROM pronunciations p "
               f"WHERE p.lexeme_id=l.id AND p.kind='ipa')",
        "a12": f"SELECT count(*) FROM lexemes l WHERE {L} AND l.cefr IN ('A1','A2')",
        "a12_audio": f"SELECT count(*) FROM lexemes l WHERE {L} AND l.cefr IN ('A1','A2') AND {has_audio}",
        "example_en": f"SELECT count(*) FROM lexemes l WHERE {L} AND EXISTS (SELECT 1 FROM examples e JOIN "
                      f"example_translations x ON x.example_id=e.id AND x.native_language='en' WHERE e.lexeme_id=l.id)",
        "cefr": f"SELECT count(*) FROM lexemes l WHERE {L} AND l.cefr IS NOT NULL",
        "nouns": f"SELECT count(*) FROM lexemes l WHERE {L} AND l.pos='noun'",
        "nouns_gender": f"SELECT count(*) FROM lexemes l WHERE {L} AND l.pos='noun' AND EXISTS (SELECT 1 FROM forms f "
                        f"WHERE f.lexeme_id=l.id AND f.field='fr_gender')",
        "a12_nouns": f"SELECT count(*) FROM lexemes l WHERE {L} AND l.pos='noun' AND l.cefr IN ('A1','A2') AND l.id <> ALL(:np)",
        "a12_nouns_img": f"SELECT count(*) FROM lexemes l WHERE {L} AND l.pos='noun' AND l.cefr IN ('A1','A2') AND l.id <> ALL(:np) AND {has_img}",
    }
    decks_sql = ("SELECT d.slug, d.cefr, d.topic, count(i.id) FROM decks d LEFT JOIN deck_items i ON i.deck_id=d.id "
                 "WHERE d.target_language='fr' AND d.published GROUP BY d.id")
    out: dict = {}
    np = no_picture_ids() or [0]
    with db.SessionLocal() as s:
        for k, sql in q.items():
            out[k] = int(s.execute(text(sql), {"w": words, "np": np}).scalar() or 0)
        out["decks"] = [tuple(r) for r in s.execute(text(decks_sql)).all()]
    return out


def ratio(a: int, b: int) -> float:
    return a / b if b else 0.0


def pct(a: int, b: int) -> str:
    return f"{100 * ratio(a, b):.1f}%（{a:,}／{b:,}）"


def data_items(words: dict[str, str], m: dict) -> dict[str, tuple[bool, str]]:
    n = len(words)
    e = m["entries"]
    theme = [d for d in m["decks"] if (d[2] or "") not in BASIC_TOPICS and d[3] >= 20]
    # a level album is a basic-words album with a level (theme albums carry a level too, they don't count); #938 keeps
    # deck.cefr empty on French basic albums, so the level may only be in the slug (fr-basic-3000-a1)
    levels = set()
    for slug, cefr, topic, size in m["decks"]:
        lv = cefr if cefr in ("A1", "A2", "B1") else (re.search(r"-(a1|a2|b1)$", slug or "") or [None, ""])[1].upper()
        if lv in ("A1", "A2", "B1") and (topic or "") in BASIC_TOPICS and size >= 20:
            levels.add(lv)
    topics = {topic for _, _, topic, size in m["decks"] if size >= 15}

    def albums(wanted: tuple[str, ...]) -> tuple[bool, str]:
        missing = [t for t in wanted if t not in topics]
        shown = f"{len(wanted) - len(missing)}/{len(wanted)} 本" + (f"，缺 {'、'.join(missing)}" if missing else "")
        return not missing, shown
    return {
        "D1": (ratio(m["present"], n) >= 0.995, pct(m["present"], n)),
        "D2": (e > 0 and m["en"] == e, pct(m["en"], e)),
        "D3": (ratio(m["ipa"], e) >= 0.995, pct(m["ipa"], e)),
        "D4": (m["a12_audio"] == m["a12"], f"缺 {m['a12'] - m['a12_audio']} 條（{pct(m['a12_audio'], m['a12'])}）"),
        "D5": (ratio(m["example_en"], e) >= 0.95, pct(m["example_en"], e)),
        "D6": (e > 0 and m["cefr"] == e, pct(m["cefr"], e)),
        "D7": (m["nouns_gender"] == m["nouns"], pct(m["nouns_gender"], m["nouns"])),
        "D8": (ratio(m["a12_nouns_img"], m["a12_nouns"]) >= 0.70, pct(m["a12_nouns_img"], m["a12_nouns"])),
        "A1": (len(theme) >= 6, f"{len(theme)} 本"),
        "A2": (levels >= {"A1", "A2", "B1"}, f"有 {'、'.join(sorted(levels)) or '0 本'}"),
        "A3": albums(THEME_TOPICS),
        "A4": albums(SITUATION_TOPICS),
    }


def board_items(issues: list[dict], tasks: list[dict], now: datetime, stuck_left: list[int]) -> dict[str, tuple[bool, str]]:
    fr_open = [i for i in issues if i.get("status") in OPEN and is_french(i.get("title") or "")]
    high = [i["id"] for i in fr_open if i.get("severity") == "high"]
    unverified = [i["id"] for i in fr_open if i.get("status") == "in_progress" and i.get("stage") not in VERIFIED]
    sim = next((t for t in tasks if int(t["id"]) == SIMULATION_CARD), None)
    if sim is None:
        p3 = (False, f"找不到卡 #{SIMULATION_CARD}")
    else:
        last = parse_iso(sim.get("last_run_at") or sim.get("updated_at"))
        n_new = new_issue_count(sim.get("progress") or "")
        fresh = last is not None and now - last <= timedelta(hours=24)
        shown = f"最近一輪 {last.astimezone(TAIPEI):%m/%d %H:%M}，新問題 {n_new if n_new is not None else '不明'}" if last else "沒跑過"
        p3 = (fresh and n_new == 0, shown)
    return {
        "P1": (not high, "沒有" if not high else "、".join(f"#{x}" for x in high[:8])),
        "P2": (not unverified, "全部過了" if not unverified else f"{len(unverified)} 張還沒過：" + "、".join(f"#{x}" for x in unverified[:8])),
        "P3": p3,
        "S1": (not stuck_left, "沒有" if not stuck_left else "排回三次還卡住：" + "、".join(f"#{x}" for x in stuck_left)),
    }


def last_mac_report() -> datetime | None:
    """When the Mac last pushed docs/mac_verify_results.md (11/03–11/09 it was offline six days and nothing said so).
    Fetches into a private ref without FETCH_HEAD so mac_sync's own fetch/merge is not disturbed."""
    import subprocess  # noqa: PLC0415
    try:
        subprocess.run(["git", "fetch", "-q", "--no-write-fetch-head", "origin", "+refs/heads/main:refs/goal/main"],
                       cwd=ROOT, capture_output=True, timeout=60)
        r = subprocess.run(["git", "log", "refs/goal/main", "-1", "--format=%ct", "--", "docs/mac_verify_results.md"],
                           cwd=ROOT, capture_output=True, text=True, timeout=30)
        ts = int((r.stdout or "").strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return datetime.fromtimestamp(ts, TAIPEI) if ts else None


def mac_item(last: datetime | None, waiting: int, now: datetime) -> tuple[bool, str]:
    shown = f"最後一次回報 {last.astimezone(TAIPEI):%m/%d %H:%M}" if last else "找不到 Mac 的回報"
    if waiting == 0:
        return True, shown + "（沒有卡在等）"
    if last is not None and now - last <= timedelta(hours=24):
        return True, shown
    return False, shown + f"，{waiting} 張在等 → 請打開 Mac 的 english_card 工作階段（Remote Control）"


def stuck_cards(tasks: list[dict], state: dict, now: datetime, hours: float, skip: set[int]) -> tuple[list[dict], list[int]]:
    """Blocked cards to requeue now, and the ones given up on (requeued REQUEUE_LIMIT times already)."""
    requeue, given_up = [], []
    for t in tasks:
        tid = int(t["id"])
        title = t.get("title") or ""
        if t.get("status") != "blocked" or tid in skip:
            continue
        if not (is_french(title) or "[owner]" in title or "[目標" in title):
            continue
        updated = parse_iso(t.get("updated_at"))
        if updated is None or now - updated < timedelta(hours=hours):
            continue
        if "停止重派" in (t.get("progress") or ""):
            continue  # the dispatcher stopped it on purpose (a repeated, already-answered decision)
        hist = state.setdefault("requeued", {}).get(str(tid), [])
        if len(hist) >= REQUEUE_LIMIT:
            given_up.append(tid)
            continue
        last = parse_iso(hist[-1]) if hist else None
        if last and now - last < timedelta(hours=24):
            continue
        requeue.append(t)
    return requeue, given_up


def issue_title(code: str, shown: str) -> str:
    name, target = ITEMS[code][0], ITEMS[code][1]
    return f"[目標 法文] {code} {name}：現在 {shown}，目標 {target}"[:300]


def filed_value(filed: str | None, title: str) -> str | None:
    """The item's value when its issue was filed: stored by this script, or, for an issue filed before that was
    stored, read back from its title 「…：現在 <value>，目標 …」 (owner-written issues have neither)."""
    if filed is not None:
        return filed
    m = re.search(r"：現在 (.+?)，目標 ", title or "")
    return m[1] if m else None


def ensure_issue(code: str, shown: str, state: dict, open_by_title: dict[str, dict], now: datetime, dry: bool) -> str:
    """Keep exactly one open issue per failing item. Returns a short note for the card.

    A closed issue whose item still fails: when its card moved the number (work done in batches, D8 52.6 → 56.8 %)
    the next round is filed at once, ROUND_LIMIT rounds at most; when nothing moved, a day later, REFILE_LIMIT times."""
    links = state.setdefault("issues", {})
    filed = state.setdefault("filed", {})
    linked = links.get(code)
    again = was = None
    if linked:
        try:
            it = http("GET", f"/issues/{linked}")
        except Exception:  # noqa: BLE001
            it = None
        if it and it.get("status") in OPEN:
            return f"#{linked}"
        was = filed_value(filed.get(code), (it or {}).get("title") or "")
        if it and was is not None and was != shown:
            if state.setdefault("rounds", {}).get(code, 0) >= ROUND_LIMIT:
                return f"#{linked} 已接著做 {ROUND_LIMIT} 輪還沒過，請看"
            again = "rounds"
        else:
            closed = parse_iso((it or {}).get("resolved_at") or (it or {}).get("updated_at"))
            if closed and now - closed < timedelta(hours=24):
                return f"#{linked} 剛結案，明天再量"
            if state.setdefault("refiled", {}).get(code, 0) >= REFILE_LIMIT:
                return f"#{linked} 結案兩次還沒過，請看"
            again = "refiled"
    for title, it in open_by_title.items():
        if title.startswith(f"[目標 法文] {code} "):
            links[code] = it["id"]
            filed.pop(code, None)
            return f"#{it['id']}"
    if dry:
        return "會接著開下一輪" if again == "rounds" else "會開新卡"
    name, target, area, severity, todo = ITEMS[code]
    before = ""
    if linked:
        before = (f"\n上一張：#{linked}（開卡時 {was or '?'}，現在 {shown}）。接著做還沒做的部分，不要重做；"
                  f"上一輪的做法和剩下的清單在看板上「問題回報 #{linked}」那張卡的 result.md。")
    body = {
        "kind": "todo", "area": area, "severity": severity, "title": issue_title(code, shown),
        "detail": (f"owner 11/10 目標「英文母語者學法文達到可以用」（lexicon/docs/goals/fr_en_usable.md）的 {code} {name} 沒過。\n"
                   f"現在：{shown}；目標：{target}。\n要做：{todo}\n"
                   "量測：python lexicon/tools/goal_check.py report。照 PIPELINE.md：改資料先備份，golden 與 QC"
                   "（qc.py check --live --target fr --native en）不退步；App 有改動要交 Mac 在 iPad 驗。" + before),
        "reporter": "目標檢查",
    }
    it = http("POST", "/issues", body)
    if again:
        counts = state.setdefault(again, {})
        counts[code] = counts.get(code, 0) + 1
    links[code] = it["id"]
    filed[code] = shown
    return f"新開 #{it['id']}" + ("（接著上一輪）" if again == "rounds" else "")


def card_text(now: datetime, results: dict[str, tuple[bool, str]], notes: dict[str, str], requeued: list[int]) -> str:
    passed = sum(1 for ok, _ in results.values() if ok)
    fails = [f"{c} {ITEMS[c][0]} {results[c][1]}" + (f"（{notes[c]}）" if c in notes else "")
             for c in ITEMS if c in results and not results[c][0]]
    s = f"{now:%m/%d %H:%M} 通過 {passed}/{len(results)}。"
    s += ("未過：" + "；".join(fails) + "。") if fails else "全部通過。"
    if requeued:
        s += "排回待辦：" + "、".join(f"#{x}" for x in requeued) + "。"
    s += f"要你做：{OWNER_ITEMS}。"
    return s[:1500]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["report", "run"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    cfg = (load_json(CONFIG, {}).get("goals") or {}).get("fr_en") or {}
    if a.cmd == "run" and not cfg.get("enabled"):
        return 0
    now = now_tw()
    state = load_json(STATE, {})
    for k, v in SEED_ISSUES.items():
        state.setdefault("issues", {}).setdefault(k, v)
    if a.cmd == "run" and not a.force and not due(state, now, float(cfg.get("every_hours", 3))):
        return 0
    dry = a.cmd == "report"

    words = basic_words()
    m = measure_db(sorted(words))
    issues = http("GET", "/issues").get("items", [])
    tasks = http("GET", "/tasks").get("items", [])
    caps = load_json(CAPS, {})
    skip = {int(x) for x in caps.get("skip_tasks", [])} | {int(x) for x in (load_json(CONFIG, {}).get("unblock_after") or {})}
    requeue, given_up = stuck_cards(tasks, state, now, float(cfg.get("stuck_hours", 12)), skip)
    done_requeue = []
    for t in requeue:
        tid = int(t["id"])
        n = len(state["requeued"].get(str(tid), [])) + 1
        if not dry:
            http("PUT", f"/tasks/{tid}", {"status": "queued", "agent": None, "by": "目標檢查",
                                         "progress": f"目標檢查 {now:%m/%d %H:%M}：卡住超過 {cfg.get('stuck_hours', 12)} 小時，自動排回待辦（第 {n} 次）"})
            state["requeued"].setdefault(str(tid), []).append(now.isoformat(timespec="seconds"))
        done_requeue.append(tid)

    results = data_items(words, m)
    results.update(board_items(issues, tasks, now, given_up))
    waiting = sum(1 for i in issues if i.get("status") == "in_progress" and i.get("stage") in ("mac_verify", "ipad_verify"))
    results["M1"] = mac_item(last_mac_report(), waiting, now)
    open_by_title = {i.get("title") or "": i for i in issues if i.get("status") in OPEN}
    notes = {}
    for code in FILED:
        if not results[code][0]:
            notes[code] = ensure_issue(code, results[code][1], state, open_by_title, now, dry)
    text = card_text(now, results, notes, done_requeue)
    print(text)
    for code, (ok, shown) in results.items():
        print(f"  {'✓' if ok else '✗'} {code} {ITEMS[code][0]}：{shown}" + (f"（{notes[code]}）" if code in notes else ""))
    if dry:
        return 0

    all_ok = all(ok for ok, _ in results.values())
    state["streak"] = state.get("streak", 0) + 1 if all_ok else 0
    state["last_run"] = now.isoformat(timespec="seconds")
    state["last"] = {"at": state["last_run"], "passed": sum(ok for ok, _ in results.values()), "total": len(results),
                     "items": {c: {"ok": ok, "shown": s, "note": notes.get(c)} for c, (ok, s) in results.items()}}
    card = cfg.get("card")
    if card:
        body = {"progress": text, "by": "目標檢查"}
        if state["streak"] >= 2:
            body["status"] = "done"
        else:
            cur = http("GET", f"/tasks/{card}")
            if cur.get("status") == "done":
                body["status"] = "scheduled"
        http("PUT", f"/tasks/{card}", body)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
