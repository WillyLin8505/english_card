import contextlib
import io
import json
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tagger'))
from inference_control import PrioritySlots, is_background
from repetition_guard import RepetitionGuard, read_cefr_stream
import tagging_server as ts


def test_background_reserves_slot_and_exception_releases_capacity():
    slots = PrioritySlots(4)
    with contextlib.ExitStack() as stack:
        with slots.request(True):
            for _ in range(3):
                stack.enter_context(slots.slot())
        entered = threading.Event()
        finished = threading.Event()

        def background():
            with slots.request(True), slots.slot():
                entered.set()
            finished.set()

        thread = threading.Thread(target=background)
        thread.start()
        assert not entered.wait(.05)
        with pytest.raises(RuntimeError), slots.slot():
            assert slots.active == 4
            raise RuntimeError('disconnected camera')
        assert slots.active == 3
        assert not entered.is_set()
    assert finished.wait(2)
    thread.join()
    assert slots.active == slots.background_active == 0


def test_single_slot_interactive_overtakes_background_queue():
    slots = PrioritySlots(1)
    order = []
    queued = threading.Event()

    def run(background):
        with slots.request(background):
            queued.set()
            with slots.slot():
                order.append(background)

    with slots.slot():
        bg = threading.Thread(target=run, args=(True,))
        bg.start()
        assert queued.wait(2)
        fg = threading.Thread(target=run, args=(False,))
        fg.start()
        with slots.condition:
            assert slots.condition.wait_for(lambda: slots.interactive_waiting == 1, timeout=2)
    bg.join(2)
    fg.join(2)
    assert order == [False, True]


@pytest.mark.parametrize('path,headers,expected', [
    ('/tag', {}, False), ('/score', {}, False), ('/translate', {}, True),
    ('/tag', {'X-Activity-Ref': 'image:71'}, True),
    ('/score', {'X-Activity-Ref': 'image:71'}, True),
    ('/tag', {'X-Inference-Priority': 'background'}, True),
])
def test_request_classification(path, headers, expected):
    assert is_background(path, headers) is expected


def response(words):
    return json.dumps({'safe': True, 'candidates': [
        {'w': word, 'p': 'n', 'x': 500, 'y': 500} for word in words]})


def test_repeat_guard_handles_token_boundaries_and_cycle():
    guard = RepetitionGuard()
    raw = response(['cup', 'table', 'cup', 'table', 'cup', 'table'] )
    for char in raw:
        if guard.feed(char):
            break
    assert guard.stopped
    parsed = ts.loads_salvaging(guard.text)
    assert {c['w'] for c in parsed['candidates']} == {'cup', 'table'}
    assert len(parsed['candidates']) == 5


def test_non_repeating_and_isolated_duplicate_are_unchanged():
    raw = response(['cup', 'cup', 'table', 'a"}b', 'wood', 'wall'])
    guard = RepetitionGuard()
    for char in raw:
        assert not guard.feed(char)
    assert guard.text == raw


def test_repeated_people_at_different_points_must_not_hide_later_labels():
    raw = json.dumps({'safe': True, 'candidates': [
        {'w': 'man', 'p': 'n', 'x': x, 'y': 100} for x in range(5)] +
        [{'w': 'mustache', 'p': 'n', 'x': 200, 'y': 100}]})
    guard = RepetitionGuard()
    assert not guard.feed(raw)
    assert guard.text == raw


def test_stream_reader_stops_consuming_after_repeated_cycle():
    raw = response(['cup', 'table', 'cup', 'table', 'cup'])
    def events():
        yield b': heartbeat\n'
        for char in raw:
            yield b'data: ' + json.dumps({'choices': [{'delta': {'content': char}}]}).encode() + b'\n'
        raise AssertionError('must stop reading before more model output')
    assert ts.loads_salvaging(read_cefr_stream(events()))['safe'] is True


def test_cefr_http_stream_is_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, 'CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(ts, 'CEFR_REPEAT_GUARD', True)
    tagger = ts.Tagger('http://unused', 'test')
    stream = io.BytesIO(b'data: ' + json.dumps({'choices': [{'delta': {
        'content': response(['cup', 'cup', 'cup', 'cup'])}}]}).encode() + b'\n')
    def open_request(req, timeout):
        payload = json.loads(req.data)
        assert payload['stream'] is True
        assert payload['max_tokens'] == 820
        return stream
    monkeypatch.setattr(ts.urllib.request, 'urlopen', open_request)
    result = tagger._chat_llamacpp('test', ts.CEFR_CANDIDATE_SCHEMA, None, 0, 820, False, True)
    assert result['safe'] is True
    assert stream.closed


def test_camera_http_request_bypasses_waiting_background_tags(monkeypatch, tmp_path):
    monkeypatch.setattr(ts, 'CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(ts, 'INFERENCE_PARALLEL', 4)
    tagger = ts.Tagger('http://unused', 'stub')

    def candidates(*args):
        with tagger._inference():
            return []

    tagger.candidates = candidates
    server = ThreadingHTTPServer(('127.0.0.1', 0), ts.make_handler(tagger, 'test-key'))
    serving = threading.Thread(target=server.serve_forever)
    serving.start()

    def post(background):
        headers = {'X-API-Key': 'test-key', 'Content-Type': 'image/jpeg'}
        if background:
            headers['X-Activity-Ref'] = 'image:71'
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/tag',
                                     data=b'image', headers=headers)
        with urllib.request.urlopen(req, timeout=3) as reply:
            return reply.status

    try:
        with ThreadPoolExecutor(2) as pool:
            with contextlib.ExitStack() as held:
                with tagger._admission.request(True):
                    for _ in range(3):
                        held.enter_context(tagger._admission.slot())
                background = pool.submit(post, True)
                camera = pool.submit(post, False)
                assert camera.result(timeout=2) == 200
                assert not background.done()
            assert background.result(timeout=2) == 200
    finally:
        server.shutdown()
        server.server_close()
        serving.join(2)
