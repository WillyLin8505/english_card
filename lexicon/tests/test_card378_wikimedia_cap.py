"""問題回報 #376: a download never sits out a long shared Wikimedia 429 pause."""
import urllib.error

import pytest

from app import images


class _Gate:
    skip_when_paused = False

    def __init__(self, paused_for, penalty):
        self.paused_for, self.penalty, self.waits, self.penalized = paused_for, penalty, 0, 0

    def status(self):
        return {'paused_for': self.paused_for}

    def wait_turn(self):
        self.waits += 1

    def penalize(self, retry_after=None):
        self.penalized += 1
        return self.penalty

    def succeeded(self):
        pass


def _patch(monkeypatch, gate):
    monkeypatch.setattr(images.rate_gate, 'gate_for', lambda url: gate)

    class Opener:
        calls = 0

        def open(self, request, timeout=0):
            Opener.calls += 1
            raise urllib.error.HTTPError(request.full_url, 429, 'robot policy', {}, None)

    monkeypatch.setattr(images.urllib.request, 'build_opener', lambda *a: Opener())
    return Opener


def test_long_existing_pause_fails_at_once(monkeypatch):
    gate = _Gate(300.0, 300.0)
    opener = _patch(monkeypatch, gate)
    with pytest.raises(urllib.error.HTTPError):
        images.fetch('https://upload.wikimedia.org/x.jpg')
    assert gate.waits == 0 and opener.calls == 0


def test_429_with_long_pause_is_not_retried(monkeypatch):
    gate = _Gate(0.0, 300.0)
    opener = _patch(monkeypatch, gate)
    with pytest.raises(urllib.error.HTTPError):
        images.fetch('https://upload.wikimedia.org/x.jpg')
    assert opener.calls == 1


def test_short_pause_retried_once(monkeypatch):
    gate = _Gate(0.0, 5.0)
    opener = _patch(monkeypatch, gate)
    with pytest.raises(urllib.error.HTTPError):
        images.fetch('https://upload.wikimedia.org/x.jpg')
    assert opener.calls == 2
