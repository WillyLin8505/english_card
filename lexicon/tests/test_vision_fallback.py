"""Codex / Cursor photo-labelling fallback (問題回報 #327, 卡 #330). Unit tests: no CLI, no DB."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import images, vision_fallback as vf


def test_to_tag_keeps_tagger_shape_and_derives_point():
    tag = vf.to_tag({'word': ' Leaf ', 'pos': 'adj', 'box': [0.9, 0.8, 0.1, 0.2],
                     'visualConfidence': 1.3}, 'codex_vision')
    assert tag == {'word': 'leaf', 'pos': 'adjective', 'box': [0.1, 0.2, 0.9, 0.8],
                   'point': [0.5, 0.5], 'source': 'codex_vision', 'visualConfidence': 1.0}
    assert vf.to_tag({'word': 'a b c d'}, 'codex_vision') is None
    assert vf.to_tag({'word': 'cup', 'pos': 'thing', 'point': [0.2, 0.3]}, 'cursor_vision')['pos'] == 'noun'
    assert vf.to_tag({'word': 'cup', 'point': [0.2, 0.3]}, 'cursor_vision')['point'] == [0.2, 0.3]


def test_parse_answer_tolerates_fences_and_rejects_prose():
    got = vf.parse_answer('```json\n{"adult": false, "candidates": [{"word": "cup"}]}\n```')
    assert got['candidates'][0]['word'] == 'cup'
    with pytest.raises(ValueError):
        vf.parse_answer('I cannot see the image.')
    with pytest.raises(ValueError):
        vf.parse_answer('{"words": []}')


def test_prompt_lists_levels_and_exclusions():
    p = vf.build_prompt(['B2', 'C1'], ['leaf', 'green'], '8-12')
    assert 'B2, C1' in p and 'leaf, green' in p and '8-12' in p


def test_reset_after_reads_the_cli_message():
    assert vf.reset_after('Weekly usage limit reached. It resets in 6 days.') == timedelta(days=6)
    assert vf.reset_after('limit reached') == timedelta(hours=5)


def test_limited_reads_dispatch_state_and_own_state(tmp_path, monkeypatch):
    now = datetime(2026, 10, 19, 1, 0, tzinfo=timezone.utc)
    dispatch, own = tmp_path / 'dispatch.json', tmp_path / 'own.json'
    monkeypatch.setattr(vf, 'DISPATCH_STATE', dispatch)
    monkeypatch.setattr(vf, 'FALLBACK_STATE', own)
    assert vf.limited('codex', now) is None
    dispatch.write_text(json.dumps({'limits': {'Codex': (now + timedelta(hours=1)).isoformat()}}))
    assert 'Codex' in vf.limited('codex', now)
    assert vf.limited('codex', now + timedelta(hours=2)) is None
    vf.mark_limited('cursor', 'resets in 2 days')
    assert vf.limited('cursor') and vf.limited('cursor', datetime.now(timezone.utc) + timedelta(days=3)) is None
    vf.remember_deferred(346)
    assert vf.deferred_ids() == {346} and 'cursor' in json.loads(own.read_text())['limits']


def test_ask_raises_quota_exhausted_on_limit_message(tmp_path, monkeypatch):
    photo = tmp_path / 'p.jpg'
    photo.write_bytes(b'\xff\xd8fake')

    def fake_run(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout=b'', stderr=b'Weekly usage limit reached. It resets in 6 days.')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    with pytest.raises(vf.QuotaExhausted):
        vf.ask('cursor', photo, 'prompt')


def test_ask_codex_reads_last_message_and_usage(tmp_path, monkeypatch):
    photo = tmp_path / 'p.jpg'
    photo.write_bytes(b'\xff\xd8fake')

    def fake_run(cmd, cwd, **kw):
        assert '--ignore-user-config' in cmd and 'read-only' in cmd and '-i' in cmd
        out = cmd[cmd.index('-o') + 1]
        with open(out, 'w', encoding='utf-8') as f:
            f.write('{"adult": false, "candidates": [{"word": "cup", "visualConfidence": 0.9}]}')
        events = b'{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":7}}\n'
        return SimpleNamespace(returncode=0, stdout=events, stderr=b'')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    got = vf.ask('codex', photo, 'prompt')
    assert got['payload']['candidates'][0]['word'] == 'cup'
    assert got['usage'] == {'input_tokens': 100, 'output_tokens': 7}


def _pipeline_stubs(monkeypatch, settled):
    levels = {'cup': 'A1', 'mug': 'A2', 'porcelain': None}
    monkeypatch.setattr(images, 'own_words', lambda s, a: set())
    monkeypatch.setattr(images, 'classify_tag_cefr', lambda s, t: {**t, 'cefr': levels.get(t['word'], 'B1')})
    monkeypatch.setattr(images, 'split_made_up', lambda s, tags, seen=(): (tags, []))
    monkeypatch.setattr(images, '_settle', lambda s, a, passed, dropped, model, done=True:
                        settled.update(passed=passed, dropped=dropped, model=model) or
                        setattr(a, 'tags', passed))
    monkeypatch.setattr(images, '_block_unsafe', lambda s, a: pytest.fail('fallback must never block'))


def test_label_uses_dictionary_levels_and_the_80_percent_rule(monkeypatch):
    settled = {}
    _pipeline_stubs(monkeypatch, settled)
    asset = SimpleNamespace(tags=[], safety_status='unchecked', tag_attempts=2, tag_error='x', tag_retry_at=1)
    answer = {'model': 'default', 'payload': {'adult': False, 'candidates': [
        {'word': 'cup', 'box': [0, 0, 1, 1], 'visualConfidence': 0.95},
        {'word': 'mug', 'visualConfidence': 0.5},
        {'word': 'porcelain', 'visualConfidence': 0.99}]}}
    got = vf.label(None, asset, [answer], 'codex')
    assert [t['word'] for t in settled['passed']] == ['cup']
    assert settled['passed'][0]['score'] == 0.95 and settled['passed'][0]['source'] == 'codex_vision'
    assert {t['word']: t['dropReason'] for t in settled['dropped']} == {
        'mug': '圖片辨識信心低於 80%', 'porcelain': '缺少 CEFR 等級'}
    assert settled['model'] == 'cefr+codex_vision:default'
    assert got['deferred'] is None and asset.tag_attempts == 0 and asset.tag_error is None


def test_label_defers_adult_flag_to_qwen(monkeypatch):
    settled = {}
    _pipeline_stubs(monkeypatch, settled)
    asset = SimpleNamespace(tags=[{'word': 'clock'}], safety_status='safe')
    got = vf.label(None, asset, [{'payload': {'adult': True, 'candidates': []}}], 'codex')
    assert got == {'deferred': 'adult', 'passed': 1} and not settled
