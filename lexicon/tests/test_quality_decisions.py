"""Owner decision 問題回報 #191: redirects, CEFR strip and correction. Unit tests."""

import importlib.util
from pathlib import Path

from app import quality as q

_spec = importlib.util.spec_from_file_location(
    "apply_quality_decisions", Path(__file__).resolve().parents[1] / "tools" / "apply_quality_decisions.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

ROWS = [(1, "tear", "noun", "full", "A2"), (2, "tear", "verb", "full", "B1"),
        (3, "tore", "unknown", "stub", "B2"), (4, "fleeing", "unknown", "stub", "B2"),
        (5, "flee", "verb", "full", "B2"), (6, "chen", "unknown", "stub", "B1"),
        (7, "laptop", "noun", "full", "C1"), (8, "grassy", "adj", "full", "C1"),
        (9, "make light of", "verb", "stub", "A1"), (10, "zorbed", "unknown", "stub", "C2")]
FLAGS = {"tore|unknown": {"inflected_form": "tear", "excluded_has_cefr": "B2"},
         "fleeing|unknown": {"inflected_form": "flee"},
         "chen|unknown": {"person_name": "人名", "excluded_has_cefr": "B1"},
         "laptop|noun": {"cefr_above_list": "B2"},
         "grassy|adj": {"common_word_too_hard": "由 grass 衍生，建議 ≤B1"},
         "make light of|verb": {"idiom_too_easy": "B2"},
         "zorbed|unknown": {"inflected_form": "zorb"},
         "missing|noun": {"person_name": "人名"}}


def test_plan_actions():
    d, log, counts = tool.plan(ROWS, FLAGS)
    assert d["redirect"] == {"3": 2, "4": 5}  # tore -> tear (verb, -ed/past pool), fleeing -> flee
    assert sorted(d["strip_cefr"]) == [6, 10]  # chen; zorbed has no lemma entry
    assert d["set_cefr"] == {"7": "B2", "8": "B1", "9": "B2"}
    assert counts["not_in_db"] == 1 and counts["set_cefr_ambiguous"] == 1
    assert any(e["action"] == "set_cefr" and e["ambiguous"] for e in log)


def _pack():
    return {"redirects": {}, "lexemes": [
        {"id": 2, "lemma": "tear", "normalized": "tear", "pos": "verb", "status": "full", "cefr": "B1",
         "senses": [{"id": 20, "images": [{"path": "a.webp"}]}], "examples": []},
        {"id": 3, "lemma": "tore", "normalized": "tore", "pos": "adj", "status": "full", "cefr": "B2",
         "senses": [{"id": 30, "images": [{"path": "b.webp"}, {"path": "a.webp"}]}],
         "examples": [{"text": "She tore the page.", "quality_flags": []},
                      {"text": "torn", "quality_flags": ["not_sentence"]}]},
        {"id": 6, "lemma": "chen", "normalized": "chen", "pos": "unknown", "status": "stub", "cefr": "B1"},
        {"id": 7, "lemma": "laptop", "normalized": "laptop", "pos": "noun", "status": "full", "cefr": "C1"}]}


def test_apply_decisions_pointer_merge_and_levels():
    pack = _pack()
    d = {"redirect": {"3": 2}, "strip_cefr": [6], "set_cefr": {"7": "B2"}}
    counts = q.apply_decisions(pack, d)
    tear, tore, chen, laptop = pack["lexemes"]
    assert tore["redirect_to"] == 2 and tore["cefr"] is None and tore["card"] == "tear"
    assert pack["redirects"]["3"] == 2
    assert [i["path"] for i in tear["senses"][0]["images"]] == ["a.webp", "b.webp"]
    assert [e["text"] for e in tear["examples"]] == ["She tore the page."]
    assert chen["cefr"] is None and chen["cefr_before_rule"] == "B1"
    assert laptop["cefr"] == "B2" and laptop["cefr_source"] == "quality_rule"
    assert counts == {"redirect": 1, "strip_cefr": 1, "set_cefr": 1,
                      "merged_images": 1, "merged_examples": 1}
    # Idempotent: a second run (serve_app after the catalog merge) adds nothing.
    q.apply_decisions(pack, d)
    assert len(tear["senses"][0]["images"]) == 2 and len(tear["examples"]) == 1
    assert chen["cefr_before_rule"] == "B1"

class RecordingSession:
    def __init__(self, redirects=()):
        self.redirects = redirects
        self.writes = []

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith('SELECT'):
            return self.redirects
        self.writes.append((sql, params))
        return []


def empty_decisions():
    return {'redirect': {}, 'strip_cefr': [], 'set_cefr': {}}


def test_reconcile_preserves_unscanned_stubs_across_runs(monkeypatch):
    previous = {'redirect': {'3': 2}, 'strip_cefr': [6, 10], 'set_cefr': {'9': 'B2'}}
    monkeypatch.setattr(q, 'load_json', lambda _: previous)
    baseline = {'lexeme_cefr': [[3, 'B2'], [6, 'B1'], [9, 'A1'], [10, 'C2']],
                'lexeme_redirects': []}
    for _ in range(2):
        decisions = empty_decisions()
        session = RecordingSession([(3, 2), (999, 2)])
        assert tool.reconcile(session, decisions, baseline, {7, 8}) == (0, 0)
        assert decisions == previous
        assert session.writes == []
        previous = decisions  # persisted decisions are the next run's input


def test_reconcile_only_undoes_evaluated_owned_decisions(monkeypatch):
    previous = {'redirect': {'3': 2, '4': 5}, 'strip_cefr': [6, 10], 'set_cefr': {}}
    monkeypatch.setattr(q, 'load_json', lambda _: previous)
    baseline = {'lexeme_cefr': [[3, 'B2'], [4, 'B2'], [6, 'B1'], [10, 'C2']],
                'lexeme_redirects': []}
    decisions = empty_decisions()
    session = RecordingSession([(3, 2), (4, 99), (999, 2)])
    assert tool.reconcile(session, decisions, baseline, {3, 4, 6, 999}) == (3, 1)
    assert decisions['strip_cefr'] == [10]
    assert session.writes[0][1] == [{'i': 3, 'c': 'B2'}, {'i': 4, 'c': 'B2'}, {'i': 6, 'c': 'B1'}]
    assert session.writes[1][1] == {'i': [3]}


def test_reconcile_keeps_other_rules_decisions_in_lint_scope(monkeypatch):
    # Card #523: calory → calorie is a #318 spelling-variant redirect and 6 a
    # #318 strip; both lexemes are in the lint scope but the lint never plans
    # them, so a re-run must carry them forward, not withdraw them.
    previous = {'redirect': {'3': 2}, 'strip_cefr': [6], 'set_cefr': {}}
    monkeypatch.setattr(q, 'load_json', lambda _: previous)
    baseline = {'lexeme_cefr': [[3, 'B2'], [6, 'B1']], 'lexeme_redirects': []}
    decisions = empty_decisions()
    session = RecordingSession([(3, 2)])
    assert tool.reconcile(session, decisions, baseline, {3, 6}, keep={3, 6}) == (0, 0)
    assert decisions == previous
    assert session.writes == []
    # Without keep the same scope withdraws both (the pre-#523 behaviour).
    decisions = empty_decisions()
    session = RecordingSession([(3, 2)])
    assert tool.reconcile(session, decisions, baseline, {3, 6}) == (2, 1)


def test_reconcile_legacy_and_missing_baseline_fail_closed(monkeypatch):
    previous = {'redirect': {}, 'strip_cefr': [6], 'set_cefr': {'7': 'B2'}}
    monkeypatch.setattr(q, 'load_json', lambda _: previous)
    for baseline in (None, {'lexeme_cefr': [[6, 'B1'], [7, 'C1']], 'lexeme_redirects': []}):
        decisions = empty_decisions()
        session = RecordingSession()
        assert tool.reconcile(session, decisions, baseline) == (0, 0)
        assert decisions == previous
        assert session.writes == []


def test_reconcile_explicit_action_replaces_previous(monkeypatch):
    monkeypatch.setattr(q, 'load_json', lambda _: {'redirect': {'3': 2}})
    decisions = {'redirect': {}, 'strip_cefr': [3], 'set_cefr': {}}
    session = RecordingSession([(3, 2)])
    assert tool.reconcile(session, decisions, {'lexeme_cefr': [[3, 'B2']], 'lexeme_redirects': []}) == (0, 1)
    assert decisions['redirect'] == {}


def test_lint_scope_requires_matching_manifest(monkeypatch):
    import hashlib
    import json
    flags = {'chen|unknown': {'person_name': 'name'}}
    manifest = {'keys': ['chen|unknown', 'laptop|noun'],
                'flags_sha256': hashlib.sha256(json.dumps(flags, sort_keys=True).encode()).hexdigest()}
    monkeypatch.setattr(q, 'load_json', lambda _: manifest)
    assert tool.lint_scope(flags, ROWS) == {7}  # clean full entries; stale stubs excluded
    assert tool.lint_scope({}, ROWS) == set()
    manifest.clear()
    assert tool.lint_scope(flags, ROWS) == set()


def test_full_pure_inflection_is_redirected_and_missing_base_is_pending():
    """#222/#223: status=full is not an independent meaning. No base row → strip,
    and the base spelling is marked 待補 instead of receiving a made-up level."""
    rows = ROWS + [(11, "brewed", "verb", "full", "C1"), (12, "brew", "verb", "full", "B2"),
                   (13, "glistening", "verb", "full", "C2"), (14, "glistening", "adj", "full", "B2")]
    flags = dict(FLAGS)
    flags["brewed|verb"] = {"inflected_form": "brew"}
    flags["glistening|verb"] = {"inflected_form": "glisten"}
    decisions, log, _ = tool.plan(rows, flags, {12, 5})
    assert decisions["redirect"]["11"] == 12
    assert "14" not in decisions["redirect"] and 14 not in decisions["strip_cefr"]
    assert 13 in decisions["strip_cefr"]
    assert tool.missing_bases(log, rows) == ["glisten", "zorb"]


def test_redirect_requires_full_translated_target():
    assert tool.pick_base([(2, 'tear', 'verb', 'stub', 'B1')], 'tore', 'verb', {2}) is None
    assert tool.pick_base(ROWS[:2], 'tore', 'verb', set()) is None
    decisions, _, _ = tool.plan(ROWS, FLAGS, {5})
    assert decisions['redirect'] == {'4': 5}
    assert 3 in decisions['strip_cefr']


def test_corrected_level_does_not_oscillate_after_clean_lint(monkeypatch):
    previous = {'redirect': {}, 'strip_cefr': [], 'set_cefr': {'7': 'B2'}}
    monkeypatch.setattr(q, 'load_json', lambda _: previous)
    decisions = empty_decisions()
    session = RecordingSession()
    assert tool.reconcile(session, decisions,
                          {'lexeme_cefr': [[7, 'C1']], 'lexeme_redirects': []}, {7}) == (0, 0)
    assert decisions == previous
    assert session.writes == []


def test_stub_exclusions_survive_real_database_reconcile(monkeypatch):
    import json
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    rows = [(i, rule, 'unknown', 'stub', 'B2')
            for i, rule in enumerate(tool.EXCLUDE, 1)]
    flags = {f'{r[1]}|unknown': {r[1]: 'excluded'} for r in rows}
    previous, _, _ = tool.plan(rows, flags)
    baseline = {'lexeme_cefr': [[r[0], r[4]] for r in rows], 'lexeme_redirects': []}
    engine = create_engine('sqlite://')
    with Session(engine) as session:
        session.execute(text('CREATE TABLE lexemes (id INTEGER PRIMARY KEY, cefr TEXT)'))
        session.execute(text('CREATE TABLE lexeme_redirects (old_id INTEGER, new_id INTEGER)'))
        session.execute(text('INSERT INTO lexemes (id, cefr) VALUES (:id, NULL)'),
                        [{'id': r[0]} for r in rows])
        for _ in range(2):
            monkeypatch.setattr(q, 'load_json', lambda _: previous)
            decisions, _, _ = tool.plan(rows, {})  # live_pack omits all stubs
            assert tool.reconcile(session, decisions, baseline, set()) == (0, 0)
            assert decisions == previous
            assert session.execute(text('SELECT count(*) FROM lexemes WHERE cefr IS NOT NULL')).scalar() == 0
            previous = json.loads(json.dumps(decisions))  # persistence round trip
    engine.dispose()
