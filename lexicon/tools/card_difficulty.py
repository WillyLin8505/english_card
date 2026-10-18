"""Card difficulty (card #156): 1 簡單 · 2 中等 · 3 困難 · 4 極難, and which AI may take a card.

    grade(card) -> (level, reason)        heuristic for a board card (task or 問題回報)
    load_capabilities() -> dict           lexicon/tools/agent_capabilities.json
    agent_profile(caps, "Codex 桌面版")    the profile whose "match" prefix fits the name
    eligible(card, profile) -> bool

The heuristic looks at scope (how many modules / issues), risk to data (batch
rewrites, migrations), whether root-cause or product judgment is needed, and
whether the work is mechanical (run an existing check and report). A level the
owner or dispatcher set on the board always wins over the heuristic.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CAPS_FILE = Path(__file__).resolve().parent / "agent_capabilities.json"
LABELS = {1: "簡單", 2: "中等", 3: "困難", 4: "極難"}

# (regex, delta, reason). Matched against title + detail, case-insensitive.
RULES: list[tuple[str, int, str]] = [
    (r"根因|root.?cause|系統性|systemic", 1, "要找根因"),
    (r"架構|重構|refactor|流程|pipeline|匯入|接入", 1, "跨模組／流程"),
    (r"migration|遷移|schema|資料庫結構", 1, "資料庫結構變更"),
    (r"批次|重寫|重算|重標|rewrite|bulk|清理|刪除|cleanup|recompute", 1, "會批次改資料"),
    (r"502|超時|timeout|效能|太慢|slow|同步|sync|併發|race", 1, "效能／同步問題"),
    (r"群組|#\d+.*#\d+.*#\d+", 1, "一張卡含多個問題"),
    (r"模擬使用者|易用性|UX|體驗|判斷|決定", 1, "需要產品判斷"),
    (r"檢查|掃描|audit|scan|抽查|check|回報數字|驗證", -1, "以檢查回報為主"),
    (r"文案|顯示|typo|拼字|說明文件|README|註解", -1, "表面修改"),
]


def grade(card: dict) -> tuple[int, str]:
    """Heuristic level 1–4 and a one-line reason for a board card dict
    (keys used: title, detail, kind, card, severity, area)."""
    text = f"{card.get('title') or ''}\n{(card.get('detail') or '')[:1500]}"
    level, why = 2, []
    seen_up = 0
    for pattern, delta, reason in RULES:
        if re.search(pattern, text, re.I):
            if delta > 0:
                seen_up += 1
                if seen_up > 2:          # cap stacking: three hard signals = 4 at most
                    continue
            level += delta
            why.append(reason)
    if card.get("kind") == "recurring" and not re.search(r"模擬|根因|修", text):
        level = min(level, 2)
        why.append("常態檢查（只回報、不大改）")
    if card.get("card") == "issue" and card.get("area") == "data" and card.get("title", "").startswith("[qc]"):
        level = max(level, 3)
        why.append("QC 規則類資料問題，修正會動大量資料")
    level = max(1, min(4, level))
    reason = "、".join(dict.fromkeys(why)) or "單一模組的一般修改"
    return level, f"{LABELS[level]}：{reason}"


def load_capabilities(path: Path | None = None) -> dict:
    return json.loads(Path(path or CAPS_FILE).read_text(encoding="utf-8"))


def agent_profile(caps: dict, name: str) -> tuple[str, dict] | tuple[None, None]:
    """('Codex', {...}) for 'Codex 桌面版'; exact key first, then match prefixes."""
    agents = caps.get("agents", {})
    if name in agents:
        return name, agents[name]
    for key, prof in agents.items():
        if any(name.startswith(p) for p in prof.get("match", [])):
            return key, prof
    return None, None


def eligible(level: int | None, profile: dict | None) -> bool:
    if not profile or profile.get("dispatchable") is False:
        return False
    return (level or 2) <= int(profile.get("max_difficulty", 0))


def model_for(profile: dict | None, level: int | None) -> str | None:
    if not profile:
        return None
    return (profile.get("models_by_difficulty") or {}).get(str(level or 2))


def effort_for(profile: dict | None, level: int | None) -> str | None:
    if not profile:
        return None
    return (profile.get("reasoning_effort_by_difficulty") or {}).get(str(level or 2))
