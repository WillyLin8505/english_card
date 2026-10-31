"""統一流程的判斷規則 (card #916, lexicon/docs/PIPELINE.md), no I/O beyond reading a result.md.

Used by flow_tick.py (stages), dispatch_tick.close_issues and sync_issue_status (an App card's
問題 stays open until iPad verification), mac_sync.app_cards (only App cards go to the Mac).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORDER = ("dev", "windows_check", "mac_verify", "ipad_verify", "ready", "released", "done")
DONE_STAGES = ("ready", "released", "done")

# A real change to the app. lexicon/backend/app/… is the lexicon server, not the App.
STRONG_RE = re.compile(r"(?<!backend/)(?<!backend\\)\bapp[/\\](?:lib|test|ios|android|macos|web|assets|pubspec)"
                       r"|\.dart\b|flutter (?:analyze|test)|需要 ?Mac[：:]", re.I)
# Words a data or tool card also uses: they count only when the card has no 問題回報 elsewhere.
WEAK_RE = re.compile(r"flutter|iOS|iPhone|畫面|Widget", re.I)


def is_app(text: str, areas: list[str] | None = None) -> bool:
    """Would rather send a card to the Mac once too often than skip verifying an App change."""
    if STRONG_RE.search(text or ""):
        return True
    return bool(WEAK_RE.search(text or "")) and (not areas or "app" in areas)


def result_text(card_id: int) -> str:
    p = ROOT / "lexicon" / "logs" / "agents" / f"card{card_id}.result.md"
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def parse_inbox(text: str) -> dict[int, tuple[str, str]]:
    """Card → (M item, commit) of its latest mac_sync hand-over: the checks passed and the code was
    pushed. 「Windows 卡 #N 交給 Mac」 items don't count, tick writes them before anything is pushed."""
    out: dict[int, tuple[str, str]] = {}
    for sec in re.split(r"(?m)^(?=## M\d+)", text):
        no = re.match(r"## (M\d+)", sec)
        commit = re.search(r"commit `([0-9a-f]{6,40})`", sec)
        if no and commit:
            for card in re.findall(r"(?m)^- 卡 #(\d+)[：:]", sec):
                out[int(card)] = (no.group(1), commit.group(1))
    return out


def item_cards(text: str) -> dict[str, list[int]]:
    """M item → its cards, for result rows that name the item instead of the card."""
    out: dict[str, list[int]] = {}
    for sec in re.split(r"(?m)^(?=## M\d+)", text):
        no = re.match(r"## (M\d+)", sec)
        if no:
            head = sec.split("\n", 1)[0]
            out[no.group(1)] = [int(n) for n in re.findall(r"(?m)^- 卡 #(\d+)[：:]", sec)
                                + re.findall(r"Windows 卡 #(\d+)", head)]
    return out


def inbox_todo(text: str) -> int:
    return len(re.findall(r"(?m)^## M\d+.*狀態：待做", text))


def todo_cards(text: str) -> set[int]:
    """Cards in M items still marked 待做: pushed, and the Mac has not reported on them."""
    return {int(c) for sec in re.split(r"(?m)^(?=## M\d+)", text)
            if re.match(r"## M\d+.*狀態：待做", sec) for c in re.findall(r"(?m)^- 卡 #(\d+)[：:]", sec)}


@dataclass
class Row:
    cards: list[int]
    verdict: str            # pass · fail · note
    device: str             # sim · ipad
    text: str
    key: str = field(default="")


def _verdict(cell: str) -> str | None:
    cell = cell.strip()
    if re.search(r"不通過|未通過", cell):
        return "fail"
    if "注意" in cell or "部分" in cell:
        return "note"
    return "pass" if cell.startswith(("通過", "✅")) else None


def _device(text: str, section: str, cell: str | None) -> str:
    """iPad only when the row (or a pure iPad section) says so: a row that never touched
    the device must not pass the iPad stage."""
    if cell:
        return "ipad" if re.search(r"iPad|實機|owner", cell) else "sim"
    if re.search(r"(還沒|尚未|沒有|未)在? ?(iPad|實機)", text):
        return "sim"
    if re.search(r"iPad|實機|owner.{0,6}手動", text):
        return "ipad"
    if "模擬器" in text or "模擬器" in section:
        return "sim"
    return "ipad" if re.search(r"iPad|實機", section) else "sim"


def _cards(first: str, items: dict[str, list[int]]) -> list[int]:
    outside = re.sub(r"（[^）]*）|\([^)]*\)", "", first)
    outside = re.sub(r"問題回報 ?#\d+", "", outside)
    item = re.match(r"M(\d+)", outside.strip())
    if item:
        return list(items.get(f"M{item.group(1)}", []))
    return [int(n) for n in re.findall(r"#(\d+)", outside)]


def parse_results(text: str, items: dict[str, list[int]] | None = None) -> list[Row]:
    """Verdict rows of docs/mac_verify_results.md, oldest first. A table counts when its
    header has a 結果 column; an optional 裝置 column beats guessing the device."""
    items = items or {}
    out, section, cols = [], "", None
    for line in text.splitlines():
        if line.startswith("## "):
            section, cols = line[3:].strip(), None
            continue
        if not line.startswith("|"):
            cols = None
            continue
        if set(line.replace("|", "").strip()) <= set("-: "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cols is None:
            cols = {c: i for i, c in enumerate(cells)}
            continue
        at = cols.get("結果")
        if at is None or at >= len(cells):
            continue
        verdict = _verdict(cells[at])
        cards = _cards(cells[0], items)
        if not verdict or not cards:
            continue
        device = cells[cols["裝置"]] if "裝置" in cols and cols["裝置"] < len(cells) else None
        raw = line.strip()
        out.append(Row(cards, verdict, _device(raw, section, device), raw,
                       hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]))
    return out


def _last(rows: list[Row], device: str) -> Row | None:
    return next((r for r in reversed(rows) if r.device == device), None)


def derive_card(status: str, app: bool, rows: list[Row], pushed: bool, released: bool = False,
                cleared: frozenset[str] | set[str] = frozenset(),
                check_failing: bool = False) -> tuple[str, str | None, str | None]:
    """(stage, state, note) from the facts alone, so a stage can never drift from them.
    `cleared`: failed rows whose follow-up 問題 is finished; they count as passed."""
    if status == "cancelled":
        return "cancelled", None, None
    if status != "done":
        return "dev", None, None
    if not app:
        return "done", None, None
    if released:
        return "released", None, None
    ipad, sim = _last(rows, "ipad"), _last(rows, "sim")
    passed = lambda r: bool(r) and (r.verdict == "pass" or r.key in cleared)  # noqa: E731
    if passed(ipad):
        return "ready", None, None
    if ipad:
        return "ipad_verify", "failed" if ipad.verdict == "fail" else "note", ipad.text[:300]
    if passed(sim):
        return "ipad_verify", None, None
    if sim:
        return "mac_verify", "failed" if sim.verdict == "fail" else "note", sim.text[:300]
    if pushed:
        return "mac_verify", None, None
    if check_failing:
        return "windows_check", "failed", "Windows 檢查沒過，修好後才會推給 Mac"
    return "windows_check", None, None


def legacy_stage(card: int, rows: list[Row], pushed: dict, todo: set[int], unpushed: set[int]) -> str | None:
    """Stage to SHOW for a card older than the pipeline (it is never rewritten): only what still waits.
    Older M items without a 待做 mark were verified by hand before the 結果 table existed."""
    if card in unpushed and card not in pushed:
        return "windows_check"
    if card not in todo:
        return None
    return derive_card("done", True, [r for r in rows if card in r.cards], True)[0]


def derive_issue(status: str, cards: list[dict]) -> tuple[str, str | None, str | None]:
    """A 問題回報 is as far along as its least finished card (`id`, `stage`, `state`, `note`)."""
    if status == "wont_fix":
        return "cancelled", None, None
    live = [c for c in cards if c["stage"] != "cancelled"]
    if not live:
        return ("done", None, None) if status == "fixed" else ("dev", None, None)
    last = min(live, key=lambda c: ORDER.index(c["stage"]))
    note = f"卡 #{last['id']}：{last['note']}" if last.get("note") else None
    return last["stage"], last.get("state"), note


def holds_issue(issue_id: int, area: str | None, card_id: int, start_issue: int, text: str | None = None) -> bool:
    """A new 問題回報 fixed by an App card is not 已修正 yet: it waits for iPad verification."""
    if not start_issue or issue_id < start_issue:
        return False
    return is_app(result_text(card_id) if text is None else text, [area] if area else None)
