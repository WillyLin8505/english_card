"""統一流程 (card #916): stages come from the facts; the App path passes the iPad, others skip the Mac."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import flow_rules as fr  # noqa: E402
import flow_tick  # noqa: E402
import sync_issue_status  # noqa: E402

H = {"X-API-Key": "test-key"}
INBOX = """
## M10（2026-11-01 10:00）狀態：待做
commit `abc1234`（Windows：flutter analyze 無 error、全過）。
- 卡 #930：改複習頁
  結果：完成
- 卡 #931：改拍照頁
  結果：完成

## M11（2026-11-01 11:00）狀態：待做（Windows 卡 #932 交給 Mac 的 App 畫面部分）
卡：還沒推的卡
"""
RESULTS = """
## 2026-11-01 M10（模擬器）

| 卡／步驟 | 結果 | 實際 | 截圖 | 嚴重度 |
|----|----|----|----|----|
| #930（#1180）複習頁 | 通過 | 流程正常 |  |  |
| #931 拍照頁 | 不通過 | 預覽黑畫面 |  | 高 |
| M334 一次加入 | 通過 | 不是這次的卡 |  |  |

## 2026-11-02 M10 iPad 實機

| 卡／步驟 | 裝置 | 結果 | 實際 |
|----|----|----|----|
| #930 複習頁 | iPad | 通過 | 正常 |
| #933 單字頁 | iPad | 注意 | 等 owner 手動確認相機 |
| #934 設定頁 | 模擬器 | 通過 | 還沒在 iPad 驗 |
"""


def rows():
    return fr.parse_results(RESULTS, fr.item_cards(INBOX))


def rows_of(card):
    return [r for r in rows() if card in r.cards]


def test_only_a_mac_sync_item_means_pushed():
    assert fr.parse_inbox(INBOX) == {930: ("M10", "abc1234"), 931: ("M10", "abc1234")}
    assert fr.inbox_todo(INBOX) == 2


def test_results_read_card_verdict_and_device():
    got = [(r.cards, r.verdict, r.device) for r in rows()]
    assert got == [([930], "pass", "sim"), ([931], "fail", "sim"), ([930], "pass", "ipad"),
                   ([933], "note", "ipad"), ([934], "pass", "sim")]


def test_row_naming_an_item_reaches_its_cards_even_a_hand_over():
    text = "## x\n| 卡 | 結果 | 實際 |\n|--|--|--|\n| M11 畫面 | 通過 | 好 |\n| M10 全部 | 通過 | 好 |\n"
    assert [r.cards for r in fr.parse_results(text, fr.item_cards(INBOX))] == [[932], [930, 931]]


def test_issue_number_in_brackets_is_not_a_card():
    assert 1180 not in rows()[0].cards


@pytest.mark.parametrize("text,area,expected", [
    ("改了 app/lib/screens/x.dart，flutter test 全過", None, True),
    ("改 lexicon/backend/app/tasks.py，沒有動 App", None, False),
    ("補了 300 筆資料，畫面上看得到", "data", False),
    ("需要 Mac：在 iPad 看一次", "data", True),
    ("畫面的文字改了", "app", True),
])
def test_app_or_not(text, area, expected):
    assert fr.is_app(text, [area] if area else None) is expected


def test_app_card_walks_every_stage():
    assert fr.derive_card("in_progress", True, [], False)[0] == "dev"
    assert fr.derive_card("done", True, [], False)[0] == "windows_check"
    assert fr.derive_card("done", True, [], False, check_failing=True)[:2] == ("windows_check", "failed")
    assert fr.derive_card("done", True, [], True)[0] == "mac_verify"
    assert fr.derive_card("done", True, rows_of(934), True)[0] == "ipad_verify"
    assert fr.derive_card("done", True, rows_of(930), True)[0] == "ready"
    assert fr.derive_card("done", True, rows_of(930), True, released=True)[0] == "released"


def test_non_app_card_skips_the_mac():
    assert fr.derive_card("done", False, [], False)[0] == "done"
    assert fr.derive_card("cancelled", True, [], False)[0] == "cancelled"


def test_failed_row_holds_the_card_until_its_follow_up_finishes():
    fail = rows_of(931)
    assert fr.derive_card("done", True, fail, True)[:2] == ("mac_verify", "failed")
    assert fr.derive_card("done", True, fail, True, cleared={fail[0].key})[0] == "ipad_verify"


def test_note_needs_a_person_and_keeps_the_stage():
    assert fr.derive_card("done", True, rows_of(933), True)[:2] == ("ipad_verify", "note")


def test_later_pass_replaces_an_earlier_failure():
    first = fr.Row([1], "fail", "ipad", "x", "k1")
    later = fr.Row([1], "pass", "ipad", "y", "k2")
    assert fr.derive_card("done", True, [first, later], True)[0] == "ready"


def test_issue_follows_its_least_finished_card():
    cards = [{"id": 1, "stage": "ready", "state": None, "note": None},
             {"id": 2, "stage": "mac_verify", "state": "failed", "note": "黑畫面"}]
    assert fr.derive_issue("in_progress", cards) == ("mac_verify", "failed", "卡 #2：黑畫面")
    assert fr.derive_issue("wont_fix", cards)[0] == "cancelled"
    assert fr.derive_issue("open", [])[0] == "dev"
    assert fr.derive_issue("fixed", [])[0] == "done"


def test_only_new_issues_of_app_cards_wait_for_the_ipad():
    assert fr.holds_issue(1200, "app", 950, 1175, text="app/lib/x.dart") is True
    assert fr.holds_issue(1100, "app", 950, 1175, text="app/lib/x.dart") is False
    assert fr.holds_issue(1200, "data", 950, 1175, text="補資料") is False


def test_sync_leaves_app_issue_open_but_fixes_old_ones(monkeypatch):
    monkeypatch.setattr(fr, "result_text", lambda _: "改了 app/lib/x.dart")
    issues = [{"id": 1200, "status": "in_progress", "area": "app"}, {"id": 1100, "status": "in_progress", "area": "app"}]
    tasks = [{"id": 950, "status": "done", "issue_ids": [1200, 1100], "progress": "好了"}]
    assert [c[:2] for c in sync_issue_status.plan(issues, tasks, 1175)] == [(1100, "fixed")]


def items():
    return {"tasks": [
        {"id": 930, "status": "done", "issue_ids": [1200], "stage": "ipad_verify", "stage_state": None, "stage_note": None},
        {"id": 940, "status": "done", "issue_ids": [1201], "stage": None, "stage_state": None, "stage_note": None},
        {"id": 941, "status": "queued", "issue_ids": [], "stage": "dev", "stage_state": None, "stage_note": None}],
        "issues": [
        {"id": 1200, "status": "in_progress", "area": "app", "stage": "ipad_verify", "stage_state": None, "stage_note": None},
        {"id": 1201, "status": "fixed", "area": "data", "stage": None, "stage_state": None, "stage_note": None}]}


def test_plan_changes_only_what_moved_and_closes_the_verified_issue():
    changes, closes = flow_tick.plan(items(), rows(), fr.parse_inbox(INBOX), set(), {}, False, text_of=lambda c: "補資料")
    assert [(c["type"], c["id"], c["stage"]) for c in changes] == [
        ("task", 930, "ready"), ("task", 940, "done"), ("issue", 1200, "ready"), ("issue", 1201, "done")]
    assert [i["id"] for i, _ in closes] == [1200]
    assert "iPad" in closes[0][1]


def test_digest_is_once_a_day_and_silent_without_work(tmp_path, monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(flow_tick, "DIGEST", tmp_path / "d.json")
    monkeypatch.setattr(flow_tick, "DIGEST_DIR", tmp_path / "days")
    morning = datetime(2026, 11, 1, 9, 5)
    assert flow_tick.write_digest(datetime(2026, 11, 1, 8, 0), ["x"], None) is False
    assert flow_tick.write_digest(morning, [], None) is False
    assert not (tmp_path / "days").exists()
    assert flow_tick.write_digest(morning.replace(day=2), ["要決定 #1"], {"checked": "2026-11-01"}) is True
    assert "要決定 #1" in (tmp_path / "days" / "2026-11-02.md").read_text(encoding="utf-8")
    assert flow_tick.write_digest(morning.replace(day=2), ["又一件"], {"checked": "2026-11-02"}) is False


def _mail_setup(tmp_path, monkeypatch, ready=True, result=None):
    sent = []
    monkeypatch.setattr(flow_tick, "DIGEST", tmp_path / "d.json")
    monkeypatch.setattr(flow_tick, "LOG", tmp_path / "flow.log")
    monkeypatch.setattr(flow_tick.gmail_send, "ready", lambda: ready)
    monkeypatch.setattr(flow_tick.gmail_send, "send", lambda subject, body: sent.append((subject, body)) or result)
    return sent


def test_digest_mail_goes_out_once_and_only_on_days_with_work(tmp_path, monkeypatch):
    from datetime import datetime
    sent = _mail_setup(tmp_path, monkeypatch)
    now = datetime(2026, 11, 2, 9, 5)
    assert flow_tick.mail_digest(now, {"checked": "2026-11-02", "date": None, "lines": []}) is False
    assert flow_tick.mail_digest(now, {"checked": "2026-11-02", "date": "2026-11-01", "lines": ["舊的"]}) is False
    state = {"checked": "2026-11-02", "date": "2026-11-02", "lines": ["要決定 #1"]}
    assert flow_tick.mail_digest(now, state) is True
    assert "1 件" in sent[0][0] and "要決定 #1" in sent[0][1]
    assert flow_tick.mail_digest(now, state) is False
    assert len(sent) == 1
    assert json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))["mailed"] == "2026-11-02"


def test_digest_without_gmail_skips_quietly(tmp_path, monkeypatch):
    from datetime import datetime
    sent = _mail_setup(tmp_path, monkeypatch, ready=False)
    state = {"checked": "2026-11-02", "date": "2026-11-02", "lines": ["要決定 #1"]}
    assert flow_tick.mail_digest(datetime(2026, 11, 2, 9, 5), state) is False
    assert sent == [] and not (tmp_path / "d.json").exists()


def test_digest_mail_failure_retries_a_few_times_then_stops(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    sent = _mail_setup(tmp_path, monkeypatch, result="寄送失敗（OSError）")
    now = datetime(2026, 11, 2, 9, 5)
    state = {"checked": "2026-11-02", "date": "2026-11-02", "lines": ["要決定 #1"]}
    assert flow_tick.mail_digest(now, state) is False
    assert state["mail_error"] == "寄送失敗（OSError）"
    flow_tick.mail_digest(now + timedelta(minutes=2), state)
    assert len(sent) == 1
    for hour in (1, 2, 3, 4):
        flow_tick.mail_digest(now + timedelta(hours=hour), state)
    assert len(sent) == flow_tick.MAIL_TRIES


def test_gmail_ready_needs_both_fields_and_failure_hides_the_server_text(monkeypatch):
    import smtplib
    from types import SimpleNamespace
    gs = flow_tick.gmail_send
    monkeypatch.setattr(gs, "_config", lambda: SimpleNamespace(GMAIL_ADDRESS="a@example.com", GMAIL_APP_PASSWORD=""))
    assert gs.ready() is False
    monkeypatch.setattr(gs, "_config", lambda: SimpleNamespace(GMAIL_ADDRESS="a@example.com", GMAIL_APP_PASSWORD="pw"))
    assert gs.ready() is True

    def boom():
        raise RuntimeError("no config")
    monkeypatch.setattr(gs, "_config", boom)
    assert gs.ready() is False

    monkeypatch.setattr(gs, "_config", lambda: SimpleNamespace(GMAIL_ADDRESS="a@example.com", GMAIL_APP_PASSWORD="pw"))
    def refused(*a, **k):
        raise smtplib.SMTPAuthenticationError(535, b"server said pw a@example.com")
    monkeypatch.setattr(smtplib, "SMTP_SSL", refused)
    reason = gs.send("s", "b")
    assert reason and "pw" not in reason.replace("應用程式密碼", "") and "example" not in reason


def test_gmail_send_mails_the_owner_themselves_with_chinese_text(monkeypatch):
    import smtplib
    from types import SimpleNamespace
    gs = flow_tick.gmail_send
    monkeypatch.setattr(gs, "_config", lambda: SimpleNamespace(GMAIL_ADDRESS="a@example.com", GMAIL_APP_PASSWORD="pw"))
    seen = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            seen["host"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            seen["login"] = user, password

        def send_message(self, msg):
            seen["msg"] = msg
            msg.as_bytes()
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    assert gs.send("每日摘要：1 件需要你", "- 要決定 #1") is None
    assert seen["host"] == ("smtp.gmail.com", 465) and seen["login"] == ("a@example.com", "pw")
    assert seen["msg"]["From"] == seen["msg"]["To"] == "a@example.com"
    assert "要決定 #1" in seen["msg"].get_content()


def test_stage_lists_agree_with_the_server():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    from app import flow
    assert set(fr.ORDER) | {"cancelled"} == set(flow.STAGES)


@pytest.fixture
def client(session, monkeypatch):
    from app import config, flow
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    monkeypatch.setattr(flow, "start_ids", lambda: {"task": 1, "issue": 1})
    monkeypatch.setattr(flow, "_load", lambda p: {"inbox_todo": 0} if p == flow.FACTS else {})
    with TestClient(app) as c:
        yield c


def _stage(client, type_, id_, stage, **kw):
    return client.post("/flow/stages", headers=H, json={"items": [{"type": type_, "id": id_, "stage": stage, **kw}]})


def test_stage_is_stored_with_history_and_old_rows_stay_null(client):
    t = client.post("/tasks", headers=H, json={"title": "新卡"}).json()
    assert t["stage"] is None
    assert _stage(client, "task", t["id"], "mac_verify").json() == {"changed": 1}
    assert _stage(client, "task", t["id"], "mac_verify").json() == {"changed": 0}
    t = client.get(f"/tasks/{t['id']}", headers=H).json()
    assert t["stage"] == "mac_verify" and t["stage_at"]
    assert t["history"][-1]["changes"][0] == {"field": "stage", "from": None, "to": "Mac 驗證"}
    assert _stage(client, "task", t["id"], "nonsense").status_code == 422


def test_overview_gate_and_needs_you(client):
    a = client.post("/tasks", headers=H, json={"title": "App 卡"}).json()
    _stage(client, "task", a["id"], "ready")
    o = client.get("/flow/overview", headers=H).json()
    assert o["tasks"]["ready"] == 1 and o["release"]["can_release"] is True
    assert any("可以發布" in x for x in o["needs_you"])

    i = client.post("/issues", headers=H, json={
        "title": "當機", "severity": "high", "area": "app", "reporter": "App 使用者（iPad）"}).json()
    client.post("/tasks", headers=H, json={"title": "修當機"})
    d = client.post("/issues", headers=H, json={"title": "要哪個？", "kind": "decision"}).json()
    b = client.post("/tasks", headers=H, json={"title": "等驗證"}).json()
    _stage(client, "task", b["id"], "ipad_verify", state="failed", note="黑畫面")
    o = client.get("/flow/overview", headers=H).json()
    assert o["release"]["can_release"] is False
    assert any(f"#{i['id']}" in r for r in o["release"]["reasons"])
    assert any(f"#{b['id']}" in r for r in o["release"]["reasons"])
    assert any(f"#{d['id']}" in x for x in o["needs_you"])
    assert [s["id"] for s in o["stuck"]] == [b["id"]]
    assert [f["id"] for f in o["feedback"]] == [i["id"]]


def test_feedback_finds_its_card(client):
    i = client.post("/issues", headers=H, json={"title": "聲音太小", "reporter": "App 使用者（iPad）"}).json()
    client.post("/issues", headers=H, json={"title": "別的"})
    t = client.post("/tasks", headers=H, json={"title": "修聲音"}).json()
    client.put(f"/tasks/{t['id']}", headers=H, json={"issue_ids": [i["id"]]})
    _stage(client, "issue", i["id"], "ipad_verify")
    rows_ = client.get(f"/flow/overview?q=%23{i['id']}", headers=H).json()["feedback"]
    assert rows_[0]["cards"] == [t["id"]] and rows_[0]["stage"] == "ipad_verify"
