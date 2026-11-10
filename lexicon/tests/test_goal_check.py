"""goal_check.py (owner 11/10: the system finds what is left for a goal by itself) — the pure parts."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import goal_check as g  # noqa: E402

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=g.TAIPEI)


def iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def test_new_issue_count_reads_the_simulation_wording():
    assert g.new_issue_count("第41輪 程式 4/4 通過；無新問題，未改程式或資料。") == 0
    assert g.new_issue_count("第 372 輪：2/2 通過；新問題 0、UX 建議 0。") == 0
    assert g.new_issue_count("新問題：無；UX 建議：無新增") == 0
    assert g.new_issue_count("新問題：2（#1601、#1602）") == 2
    assert g.new_issue_count("新問題 10 個") == 10
    assert g.new_issue_count("只跑測試") is None


def test_due_every_n_hours():
    assert g.due({}, NOW, 3)
    assert not g.due({"last_run": iso(1)}, NOW, 3)
    assert g.due({"last_run": iso(3.5)}, NOW, 3)


def card(tid, title, status="blocked", hours_ago=13, progress=""):
    return {"id": tid, "title": title, "status": status, "updated_at": iso(hours_ago), "progress": progress}


def test_stuck_cards_requeues_owner_and_french_cards_only():
    tasks = [
        card(1, "[owner] 補齊英文關聯詞"),
        card(2, "問題回報 #1556：[owner] 法文主題相片冊"),
        card(3, "常態：全庫掃描"),                         # neither owner nor French
        card(4, "[owner] 剛卡住", hours_ago=1),             # not long enough
        card(5, "[owner] 在跳過名單"),                      # skip_tasks / unblock_after
        card(6, "[owner] 重複的決策", progress="重複提出已處理的決策 #9，停止重派"),
        card(7, "[owner] 排回三次了"),
        card(8, "[owner] 今天排回過"),
        card(9, "[owner] 在做", status="in_progress"),
    ]
    state = {"requeued": {"7": [iso(90), iso(60), iso(30)], "8": [iso(2)]}}
    requeue, given_up = g.stuck_cards(tasks, state, NOW, 12, skip={5})
    assert [t["id"] for t in requeue] == [1, 2]
    assert given_up == [7]


def test_data_items_counts_theme_and_level_albums():
    words = {f"w{i}": "A1" for i in range(100)}
    m = {"present": 100, "entries": 120, "en": 120, "ipa": 120, "a12": 50, "a12_audio": 49, "example_en": 115,
         "cefr": 120, "nouns": 60, "nouns_gender": 60, "a12_nouns": 40, "a12_nouns_img": 30,
         "decks": [("fr-basic-3000", None, "法語基礎字", 3000), ("fr-animals", "A1", "動物", 25),
                   ("fr-food", "A2", "食物", 12), ("fr-a1", "A1", "法語基礎字", 500)]}
    r = g.data_items(words, m)
    assert r["D2"][0] and r["D5"][0] and r["D8"][0]          # 115/120 = 95.8 %, 30/40 = 75 %
    assert not r["D4"][0] and "缺 1 條" in r["D4"][1]
    assert not r["A1"][0] and r["A1"][1] == "1 本"            # food has < 20 words; basic topics don't count
    assert not r["A2"][0] and r["A2"][1] == "有 A1"           # the animals album's A1 is a theme, not a level album
    m["decks"] += [("fr-basic-3000-a2", None, "法語基礎字", 779), ("fr-basic-3000-b1", None, "法語基礎字", 1402)]
    r = g.data_items(words, m)
    assert r["A2"][0]                                        # #938: level only in the slug, cefr empty
    assert r["D1"][1] == "100.0%（100／100）"                 # the album loop must not touch the word count


def test_theme_and_situation_albums_match_topic_names():
    words = {"w": "A1"}
    base = {"present": 1, "entries": 1, "en": 1, "ipa": 1, "a12": 1, "a12_audio": 1, "example_en": 1, "cefr": 1,
            "nouns": 1, "nouns_gender": 1, "a12_nouns": 1, "a12_nouns_img": 1}
    themes = [(f"fr-t{i}", None, t, 15) for i, t in enumerate(g.THEME_TOPICS)]
    r = g.data_items(words, {**base, "decks": themes})
    assert r["A3"] == (True, f"{len(g.THEME_TOPICS)}/{len(g.THEME_TOPICS)} 本")
    assert not r["A4"][0] and r["A4"][1].startswith("0/8 本，缺 在餐廳")
    themes[0] = ("fr-t0", None, "季節", 14)                          # too small to count
    assert g.data_items(words, {**base, "decks": themes})["A3"][1].endswith("缺 季節")


def test_mac_item_flags_a_silent_mac_only_when_cards_wait():
    assert g.mac_item(NOW - timedelta(days=6), 0, NOW)[0]            # nothing waiting: silence is fine
    assert g.mac_item(NOW - timedelta(hours=5), 7, NOW)[0]
    ok, shown = g.mac_item(NOW - timedelta(days=6), 7, NOW)          # 11/03–11/09: offline with cards waiting
    assert not ok and "7 張在等" in shown and "Mac" in shown
    assert not g.mac_item(None, 3, NOW)[0]


def test_card_text_lists_failures_and_owner_items():
    results = {"D1": (True, "99.9%"), "D4": (False, "缺 7 條"), "P3": (True, "新問題 0")}
    text = g.card_text(NOW, results, {"D4": "#1555"}, [831])
    assert text.startswith("11/10 09:00 通過 2/3。")
    assert "D4 A1／A2 音檔 缺 7 條（#1555）" in text and "#831" in text and "#1540" in text
