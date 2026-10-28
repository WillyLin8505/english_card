import threading
import time

from lexicon_transport import RequestWatch


def test_slow_and_stuck_requests_are_logged(tmp_path):
    log = tmp_path / 'slow.log'
    w = RequestWatch(log, slow_s=0.05, stuck_s=0.05)
    done = threading.Event()

    def req():
        k = w.begin('GET', '/api/decks', 'h')
        done.wait(2)
        w.end(k, 200)
    t = threading.Thread(target=req)
    t.start()
    time.sleep(0.15)
    w.check()
    done.set()
    t.join()
    text = log.read_text(encoding='utf-8')
    assert 'STUCK GET /api/decks' in text and 'SLOW GET /api/decks' in text


def test_fast_request_is_not_logged(tmp_path):
    w = RequestWatch(tmp_path / 'l.log', slow_s=5)
    w.end(w.begin('GET', '/x'), 200)
    assert not (tmp_path / 'l.log').exists()
