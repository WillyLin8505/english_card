"""問題回報: create, filter, decide, close, and the change history."""

import pytest
from fastapi.testclient import TestClient

H = {"X-API-Key": "test-key"}


@pytest.fixture
def client(session, monkeypatch):
    from app import config
    from app.main import app
    monkeypatch.setattr(config, "API_KEY", "test-key")
    with TestClient(app) as c:
        yield c


def test_issue_lifecycle(client):
    r = client.post("/issues", headers=H, json={
        "title": "翻面後沒有播放發音", "area": "app", "severity": "high",
        "steps": "1. 開始複習\n2. 按顯示答案", "reporter": "claude-simulation"})
    assert r.status_code == 201
    bug = r.json()
    assert bug["status"] == "open" and bug["history"][0]["note"] == "建立"

    q = client.post("/issues", headers=H, json={
        "title": "沒有卡片時要不要自動加入詞庫單字？", "kind": "decision",
        "options": ["自動加入 A1 單字", "維持空白，提示去拍照"]}).json()
    assert q["status"] == "needs_decision" and len(q["options"]) == 2

    listed = client.get("/issues?status=active", headers=H).json()
    assert [i["id"] for i in listed["items"]] == [q["id"], bug["id"]]  # decisions first
    assert listed["counts"] == {"bug:open": 1, "decision:needs_decision": 1}

    d = client.post(f"/issues/{q['id']}/decide", headers=H,
                    json={"decision": "維持空白，提示去拍照"}).json()
    assert d["status"] == "open" and d["decision"] == "維持空白，提示去拍照"
    assert d["history"][-1]["by"] == "owner"

    fixed = client.put(f"/issues/{bug['id']}", headers=H,
                       json={"status": "fixed", "resolution": "翻面時呼叫 speaker.say"}).json()
    assert fixed["resolved_at"] and fixed["history"][-1]["changes"][0]["to"] == "fixed"
    assert client.get("/issues?status=closed", headers=H).json()["items"][0]["id"] == bug["id"]
    assert client.get("/issues?q=發音", headers=H).json()["items"][0]["id"] == bug["id"]

    reopened = client.put(f"/issues/{bug['id']}", headers=H, json={"status": "open"}).json()
    assert reopened["resolved_at"] is None


def test_issue_validation(client):
    assert client.post("/issues", headers=H, json={"title": " "}).status_code == 422
    assert client.post("/issues", headers=H, json={"title": "x", "area": "moon"}).status_code == 422
    assert client.put("/issues/999", headers=H, json={"status": "fixed"}).status_code == 404
    assert client.get("/issues").status_code == 401
    i = client.post("/issues", headers=H, json={"title": "x"}).json()
    assert client.delete(f"/issues/{i['id']}", headers=H).status_code == 204
    assert client.get(f"/issues/{i['id']}", headers=H).status_code == 404
