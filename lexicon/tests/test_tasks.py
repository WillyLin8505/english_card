"""排程: requests, which AI takes them, and what runs in the background."""

import pytest
from fastapi.testclient import TestClient

H = {"X-API-Key": "test-key"}


@pytest.fixture
def client(session, monkeypatch):
    from app import config
    from app import tasks
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    tasks.clear_slow_cache()
    with TestClient(app) as c:
        yield c


def test_a_request_is_taken_by_an_ai_and_finished(client):
    r = client.post("/tasks", headers=H, json={"title": "做一個排程頁面", "detail": "看 AI 在做什麼"})
    assert r.status_code == 201
    t = r.json()
    assert (t["status"], t["agent"], t["requested_by"]) == ("queued", None, "owner")

    t = client.put(f"/tasks/{t['id']}", headers=H, json={
        "status": "in_progress", "agent": "Claude · 語言資料後台", "progress": "寫 API"}).json()
    assert t["started_at"] and not t["finished_at"] and not t["stale"]
    agents = client.get("/tasks/agents", headers=H).json()["items"]
    assert [(a["agent"], [d["title"] for d in a["doing"]]) for a in agents if a["agent"] != "Qwen"] == [  # Qwen is always listed (card #61)
        ("Claude · 語言資料後台", ["做一個排程頁面"])]

    t = client.put(f"/tasks/{t['id']}", headers=H, json={
        "status": "done", "progress": "完成", "issue_ids": [169], "by": "Claude · 語言資料後台"}).json()
    assert t["finished_at"] and t["issue_ids"] == [169]
    # Who changed what, in order; the history names the AI.
    assert [h["by"] for h in t["history"]] == ["owner", "Claude · 語言資料後台", "Claude · 語言資料後台"]
    assert client.get("/tasks?status=active", headers=H).json()["items"] == []
    assert client.put(f"/tasks/{t['id']}", headers=H, json={"status": "maybe"}).status_code == 422


def test_background_reports_qwen_even_when_the_tagger_is_down(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "AI_URL", "http://127.0.0.1:9")  # nothing listens here
    bg = client.get("/schedule/background", headers=H).json()
    assert bg["qwen"]["ok"] is False and bg["jobs"] == []
    assert set(bg["pictures"]) >= {"pending", "labelled_last_hour", "labelled_since_pause",
                                   "downloads_waiting"}
    assert bg["pictures"]["labelled_since_pause"] is None or isinstance(
        bg["pictures"]["labelled_since_pause"], int)


def test_an_idle_ai_pulls_the_top_card_and_issues_are_cards_too(client):
    # An open 問題回報 is a card in the deck until an AI takes it.
    issue = client.post("/issues", headers=H, json={"title": "翻面後沒有發音", "kind": "bug",
                                                     "severity": "high"}).json()
    req = client.post("/tasks", headers=H, json={"title": "排程改成看板"}).json()
    deck = client.get("/schedule/board", headers=H).json()["deck"]
    assert [(c["card"], c.get("id") or c.get("issue_id")) for c in deck] == [
        ("task", req["id"]), ("issue", issue["id"])]

    # 「tasks.py next」: the top card first.
    got = client.post("/schedule/claim", headers=H, json={"agent": "Codex 桌面版"}).json()
    assert (got["id"], got["status"], got["agent"]) == (req["id"], "in_progress", "Codex 桌面版")
    # Then the issue: a task linked to it, and the issue shows it's being worked on.
    got = client.post("/schedule/claim", headers=H, json={"agent": "Claude · UI"}).json()
    assert got["issue_ids"] == [issue["id"]] and got["requested_by"] == "問題回報"
    assert client.get(f"/issues/{issue['id']}", headers=H).json()["status"] == "in_progress"
    assert client.get("/schedule/board", headers=H).json()["deck"] == []
    assert client.post("/schedule/claim", headers=H, json={"agent": "Claude · UI"}).status_code == 404
    # Someone else's card can't be taken from them.
    assert client.post("/schedule/claim", headers=H, json={
        "agent": "Claude · UI", "task_id": req["id"]}).status_code == 409

    bots = {b["agent"]: b["state"] for b in client.get("/schedule/board", headers=H).json()["bots"]
            if b["agent"] != "Qwen"}  # Qwen is always listed (card #61)
    assert bots == {"Codex 桌面版": "working", "Claude · UI": "working"}


def test_a_standing_card_comes_back_after_each_run(client):
    card = client.post("/tasks", headers=H, json={
        "title": "掃描未完成的圖片標籤", "kind": "recurring", "interval_minutes": 60,
        "metric": "labels_pending"}).json()
    assert (card["status"], card["due"]) == ("scheduled", True)
    board = client.get("/schedule/board", headers=H).json()
    assert board["recurring"][0]["metric_value"]["value"] == 0
    assert board["deck"][0]["id"] == card["id"]          # due: top of the deck

    client.post("/schedule/claim", headers=H, json={"agent": "Claude · A", "task_id": card["id"]})
    done = client.put(f"/tasks/{card['id']}", headers=H, json={
        "status": "done", "progress": "沒有卡住的圖片", "by": "Claude · A"}).json()
    assert (done["status"], done["agent"], done["last_result"], done["due"]) == (
        "scheduled", None, "沒有卡住的圖片", False)
    assert done["next_run_at"] and client.get("/schedule/board", headers=H).json()["deck"] == []


def test_a_card_dragged_onto_an_ai_waits_under_it_and_comes_first(client):
    first = client.post("/tasks", headers=H, json={"title": "最上面的卡"}).json()
    issue = client.post("/issues", headers=H, json={"title": "標籤分級錯", "kind": "bug"}).json()
    handed = client.post("/schedule/assign", headers=H, json={
        "agent": "Claude · UI", "issue_id": issue["id"]}).json()
    assert (handed["status"], handed["agent"]) == ("queued", "Claude · UI")
    board = client.get("/schedule/board", headers=H).json()
    assert [c.get("id") for c in board["deck"]] == [first["id"]]   # no longer in the deck
    assert [t["id"] for t in board["bots"][0]["assigned"]] == [handed["id"]]
    # Its next card is the one handed to it, not the deck's top.
    got = client.post("/schedule/claim", headers=H, json={"agent": "Claude · UI"}).json()
    assert got["id"] == handed["id"]
    assert client.get(f"/issues/{issue['id']}", headers=H).json()["status"] == "in_progress"


def test_an_ai_can_pull_from_one_pile_only(client):
    once = client.post("/tasks", headers=H, json={"title": "一次性的需求"}).json()
    standing = client.post("/tasks", headers=H, json={"title": "掃描", "kind": "recurring"}).json()
    got = client.post("/schedule/claim", headers=H, json={"agent": "A", "pile": "once"}).json()
    assert got["id"] == once["id"]          # though the due standing card is on top overall
    got = client.post("/schedule/claim", headers=H, json={"agent": "B", "pile": "recurring"}).json()
    assert got["id"] == standing["id"]
    assert client.post("/schedule/claim", headers=H, json={"agent": "C", "pile": "x"}).status_code == 422


def test_the_board_shows_unchecked_pictures_but_never_blocked_ones(client, tmp_path, monkeypatch):
    from app import config, db, models as m
    monkeypatch.setattr(config, "MEDIA", tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"jpeg")
    with db.session_scope() as s:
        ids = []
        for safety in ("unchecked", "blocked"):
            a = m.ImageAsset(source="wikimedia_commons", source_image_id=f"File:{safety}.jpg", license_code="CC0",
                             status="ready", path="a.jpg", mime="image/jpeg", safety_status=safety)
            s.add(a)
            s.flush()
            ids.append(a.id)
    assert client.get(f"/schedule/picture/{ids[0]}", headers=H).content == b"jpeg"
    assert client.get(f"/schedule/picture/{ids[1]}", headers=H).status_code == 404
    assert client.get(f"/schedule/picture/{ids[0]}").status_code == 401   # the owner's board only


def test_cards_carry_a_difficulty_and_the_ai_panel_has_capabilities(client, monkeypatch):
    # Card #156: a difficulty on tasks and on 問題回報 cards, set from the board.
    t = client.post("/tasks", headers=H, json={"title": "加難度欄位", "difficulty": 3,
                                               "difficulty_reason": "跨模組"}).json()
    assert (t["difficulty"], t["difficulty_reason"]) == (3, "跨模組")
    t = client.put("/schedule/difficulty", headers=H, json={"task_id": t["id"], "difficulty": 2,
                                                            "reason": "其實只有一個模組", "by": "Grokbot"}).json()
    assert t["difficulty"] == 2 and t["history"][-1]["by"] == "Grokbot"
    issue = client.post("/issues", headers=H, json={"title": "照片標籤太少", "kind": "bug"}).json()
    client.put("/schedule/difficulty", headers=H, json={"issue_id": issue["id"], "difficulty": 4, "reason": "全庫"})
    deck = {(c["card"], c.get("id") or c.get("issue_id")): c for c in client.get("/schedule/board", headers=H).json()["deck"]}
    assert deck[("issue", issue["id"])]["difficulty"] == 4
    # Claiming the issue carries its difficulty onto the new task.
    got = client.post("/schedule/claim", headers=H, json={"agent": "Codex", "issue_id": issue["id"]}).json()
    assert (got["difficulty"], got["difficulty_reason"]) == (4, "全庫")
    assert client.put("/schedule/difficulty", headers=H, json={"task_id": t["id"], "difficulty": 5}).status_code == 422
    assert client.put("/schedule/difficulty", headers=H, json={"difficulty": 1}).status_code == 422
    assert client.get("/tasks/meta", headers=H).json()["difficulties"]["4"] == "極難"

    # Card #157: capabilities + usage for the AI panel, never failing the request.
    from app import agent_usage
    monkeypatch.setattr(agent_usage, "collect", lambda force=False: {"agents": {"Codex": {"five_hour": None}}})
    info = client.get("/schedule/agents-info", headers=H).json()
    assert "Claude Code" in info["capabilities"]["agents"] and "Codex" in info["usage"]["agents"]


def test_board_cards_carry_only_recent_history(client):
    """Card #445: the board stays small; GET /tasks/<id> has the whole record."""
    t = client.post("/tasks", headers=H, json={"title": "很多紀錄的卡"}).json()
    for k in range(8):
        client.put(f"/tasks/{t['id']}", headers=H, json={"progress": f"第 {k} 步", "by": "Codex 桌面版"})
    deck = {c.get("id"): c for c in client.get("/schedule/board", headers=H).json()["deck"]}
    card = deck[t["id"]]
    full = client.get(f"/tasks/{t['id']}", headers=H).json()
    assert len(full["history"]) == card["history_n"] >= 9
    assert card["history"] == full["history"][-3:]
