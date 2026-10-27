"""Regression coverage for card #674: never finalize an incomplete model reply."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("card631_relocate", Path(__file__).parents[1] / "tools" / "card631_relocate.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


def reply(words, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps({"items": [
        {"word": w, "visible": True, "box": [100, 200, 300, 400]} for w in words]})}}]}


def test_length_is_rejected_even_with_parseable_json():
    with pytest.raises(r.IncompleteReply, match="finish_reason=length"):
        r.validate_reply(reply(["tree"], "length"), ["tree"])


@pytest.mark.parametrize("content", ['{"items":[', '{"items":[]}', '{"items":null}'])
def test_invalid_or_missing_items_stay_pending(content):
    data = reply(["tree"])
    data["choices"][0]["message"]["content"] = content
    with pytest.raises(r.IncompleteReply):
        r.validate_reply(data, ["tree"])


@pytest.mark.parametrize("items", [
    [{"word": "other", "visible": False, "box": []}],
    [{"word": "tree", "visible": "false", "box": []}],
    [{"word": "tree", "visible": True, "box": [0, 1, 2]}],
    [{"word": "tree", "visible": True, "box": [0, 1, 2, float("nan")]}],
    [{"word": "tree", "visible": False, "box": [0, 1, 2, 3]}],
])
def test_bad_label_or_geometry_rejected(items):
    data = reply(["tree"])
    data["choices"][0]["message"]["content"] = json.dumps({"items": items})
    with pytest.raises(r.IncompleteReply):
        r.validate_reply(data, ["tree"])


def test_groups_retry_with_larger_budget(monkeypatch):
    calls = []
    def ask(img, words, budget):
        calls.append((list(words), budget))
        if len(calls) == 1:
            raise r.IncompleteReply("length")
        return r.validate_reply(reply(words), words)
    monkeypatch.setattr(r, "ask", ask)
    words = [f"word{i}" for i in range(17)]
    result = r.locate(b"image", words)
    assert len(result) == 17
    assert [len(w) for w, _ in calls] == [6, 6, 6, 5]
    assert calls[1][1] == 2 * calls[0][1]


def test_group_failure_is_bounded_and_no_partial_result(monkeypatch):
    calls = []
    def ask(img, words, budget):
        calls.append(words)
        if len(calls) > 1:
            raise r.IncompleteReply("length")
        return r.validate_reply(reply(words), words)
    monkeypatch.setattr(r, "ask", ask)
    with pytest.raises(r.IncompleteReply):
        r.locate(b"image", [f"word{i}" for i in range(17)])
    assert len(calls) == 3


def test_failures_survive_restart_and_eventually_require_explicit_retry(tmp_path):
    tags = [{"word": "tree", "point": [0.5, 0.5]}]
    state = {}
    for i in range(3):
        now = i * (r.COOLDOWN + 1)
        assert r.eligible(state, 845, tags, now)
        r.record_failure(state, 845, tags, "length", now)
        r.save_state(state, tmp_path / "state.json")
        state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert not r.eligible(state, 845, tags, now + 1)
    assert not r.eligible(state, 845, tags, 10 * r.COOLDOWN)
    assert r.eligible(state, 845, tags, 10 * r.COOLDOWN, retry_failed=True)
    assert r.eligible(state, 845, tags + [{"word": "rock"}], 10 * r.COOLDOWN)
    assert r.pending(tags) == tags


def test_case_matching_and_existing_tags_preserved():
    tags = [{"word": "Tree", "point": [0.5, 0.5], "custom": "keep"},
            {"word": "mood", "point": [0.5, 0.4]},
            {"word": "rock", "point": [0.2, 0.3]}]
    result = r.validate_reply(reply(["TREE"]), ["Tree"])
    result.append({"word": "mood", "visible": False, "box": []})
    updated, boxed, whole = r.relocated_tags(tags, r.pending(tags), result)
    assert (boxed, whole) == (1, 1)
    assert updated[0]["point"] == [0.2, 0.3]
    assert updated[0]["custom"] == "keep"
    assert updated[1]["pointUngrounded"] is True
    assert updated[2] == tags[2]
    assert "box" not in tags[0]


def test_duplicate_word_rejected():
    with pytest.raises(r.IncompleteReply):
        r.validate_reply(reply(["tree", "tree"]), ["tree", "rock"])


def test_paused_qwen_never_submits_request(monkeypatch):
    monkeypatch.setattr(r, "paused_agents", lambda **kwargs: {"Qwen": "paused"})
    monkeypatch.setattr(r.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("submitted while paused"))
    with pytest.raises(RuntimeError, match="paused"):
        r.ask(b"image", ["tree"], 1024)


def test_review_hold_survives_cooldown():
    tags = [{"word": "pitch", "point": [0.5, 0.5]}]
    state = {"845": {"fingerprint": r.fingerprint(tags), "review_issue": 784}}
    assert not r.eligible(state, 845, tags, 10 * r.COOLDOWN)
    assert r.eligible(state, 845, tags, 10 * r.COOLDOWN, retry_failed=True)


def test_picture_deadline_prevents_another_request(monkeypatch):
    times = iter([0, 151])
    monkeypatch.setattr(r.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(r, "ask", lambda *args: pytest.fail("request exceeded picture deadline"))
    with pytest.raises(r.IncompleteReply, match="time budget"):
        r.locate(b"image", ["tree"])


def test_case_variants_share_one_model_label(monkeypatch):
    def ask(img, words, budget):
        assert words == ["Tree"]
        return r.validate_reply(reply(words), words)
    monkeypatch.setattr(r, "ask", ask)
    assert len(r.locate(b"image", ["Tree", "tree"])) == 1


@pytest.mark.parametrize("box", [[-10, 0, 400, 400], [400, 200, 100, 400], [0, 0, 1000, 1000], [0, 0, 20, 100]])
def test_unreliable_boxes_never_become_whole_picture(box):
    tags = [{"word": "pitch", "point": [0.5, 0.5]}]
    with pytest.raises(ValueError):
        r.relocated_tags(tags, tags, [{"word": "pitch", "visible": True, "box": box}])
    assert tags == [{"word": "pitch", "point": [0.5, 0.5]}]


def test_review_is_bound_to_image_tags_and_exact_proposal():
    tags = [{"word": "pitch", "point": [0.5, 0.5]}]
    p = {"id": 845, "fingerprint": r.fingerprint(tags),
         "image_sha256": r.hashlib.sha256(b"image").hexdigest(),
         "items": [{"word": "pitch", "visible": True, "box": [35, 478, 963, 520]}],
         "reviewer": "", "approved_digest": ""}
    with pytest.raises(ValueError, match="Visual review"):
        r.reviewed_items(p, 845, tags, b"image")
    p["reviewer"] = "test reviewer"
    p["approved_digest"] = r.review_digest(p)
    assert r.reviewed_items(p, 845, tags, b"image") == p["items"]
    with pytest.raises(ValueError, match="stale"):
        r.reviewed_items(p, 845, tags, b"changed image")
    with pytest.raises(ValueError, match="stale"):
        r.reviewed_items(p, 845, tags + [{"word": "new"}], b"image")
    p["items"][0]["box"][0] = 100
    with pytest.raises(ValueError, match="Visual review"):
        r.reviewed_items(p, 845, tags, b"image")
