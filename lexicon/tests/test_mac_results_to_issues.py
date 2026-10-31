"""Card #918: every Mac verdict reaches the system; 注意 rows become todos, once per item."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import mac_results_to_issues as m  # noqa: E402

RESULTS = """
## 2026-11-01 M10（iPad）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #930 複習頁 | 通過 | 正常 |  |  |
| #931 拍照頁 | 不通過 | 預覽被切掉 |  | 中 |
| 本機標籤品質 | 注意 | 標籤偏分類詞 |  |  |
| #932 圖片 | 注意 | 還沒在 iPad 驗，等下一輪 |  |  |
| #933 價格 | 注意 | owner 在 #1 選 A（不動） |  |  |
"""


def test_note_rows_need_no_card_number_and_skip_waiting_rows():
    notes = m.note_rows(RESULTS)
    assert len(notes) == 1 and "本機標籤品質" in notes[0][1]
    assert notes[0][0].startswith("2026-11-01 M10")


def test_failure_rows_still_found_and_passes_ignored():
    fails = m.failure_rows(RESULTS)
    assert len(fails) == 1 and "#931" in fails[0][1]


def test_same_item_has_one_key_whatever_the_verdict():
    a = "| 本機標籤品質 | 注意 | A |  |  |"
    b = "| 本機標籤品質 | 不通過 | B |  |  |"
    assert m.item_key(a) == m.item_key(b) != m.item_key("| 另一項 | 注意 | A |  |  |")


def test_main_files_note_once_and_not_while_item_is_open(tmp_path, monkeypatch):
    posts, status = [], {"v": "open"}
    monkeypatch.setattr(m, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(m, "sh", lambda *a: RESULTS if a[:2] == ("git", "show") else "")

    def http(method, path, body=None):
        if method == "POST":
            posts.append(body)
            return {"id": 100 + len(posts)}
        return {"status": status["v"]}

    monkeypatch.setattr(m, "http", http)
    assert m.main([]) == 0
    kinds = sorted((p["kind"], p["severity"]) for p in posts)
    assert kinds == [("bug", "medium"), ("todo", "low")]
    assert any(p["title"].startswith("[Mac 注意]") for p in posts)
    m.main([])
    assert len(posts) == 2  # row hash remembered
    # fixed row re-reported with different text while the old issue is open → no duplicate
    monkeypatch.setattr(m, "sh", lambda *a: RESULTS.replace("標籤偏分類詞", "仍偏分類詞") if a[:2] == ("git", "show") else "")
    m.main([])
    assert len(posts) == 2
    monkeypatch.setattr(m, "sh", lambda *a: RESULTS.replace("標籤偏分類詞", "第三次還是偏") if a[:2] == ("git", "show") else "")
    status["v"] = "fixed"  # closed → a new report is a new issue
    m.main([])
    assert len(posts) == 3
    assert json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))["filed"]
