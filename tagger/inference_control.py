"""Admission control shared by every model call in one tagger process."""
import contextlib
import json
import threading
import time
from pathlib import Path


class PrioritySlots:
    def __init__(self, capacity):
        self.capacity = max(1, capacity)
        self.background_limit = max(1, self.capacity - 1)
        self.active = self.background_active = self.interactive_waiting = 0
        self.condition = threading.Condition()
        self.local = threading.local()

    @contextlib.contextmanager
    def request(self, background=False):
        previous = getattr(self.local, "background", False)
        self.local.background = background
        try:
            yield
        finally:
            self.local.background = previous

    @contextlib.contextmanager
    def slot(self):
        background = getattr(self.local, "background", False)
        with self.condition:
            if not background:
                self.interactive_waiting += 1
            try:
                self.condition.wait_for(lambda: self.active < self.capacity and (
                    not background or (self.background_active < self.background_limit
                                       and self.interactive_waiting == 0)))
                self.active += 1
                self.background_active += int(background)
            finally:
                if not background:
                    self.interactive_waiting -= 1
                self.condition.notify_all()
        try:
            yield
        finally:
            with self.condition:
                self.active -= 1
                self.background_active -= int(background)
                self.condition.notify_all()


def is_background(path, headers):
    # Existing workers already send image:<id>, including their /score rounds.
    # Explicit priority also covers standalone import tools. Unmarked App
    # camera calls remain interactive without requiring an App upgrade.
    return (path == "/translate"
            or headers.get("X-Inference-Priority", "").lower() == "background"
            or headers.get("X-Activity-Ref", "").startswith("image:"))


# Board pause for the local model (name "Qwen"). Written by the lexicon
# backend when the owner presses pause on the schedule board.
_PAUSED_FILE = Path(__file__).resolve().parents[1] / "lexicon" / "state" / "paused_agents.json"
_PAUSED_CACHE = {"at": 0.0, "paused": False}


def is_qwen_paused(max_age: float = 3.0) -> bool:
    """True when the owner paused Qwen on the board. Cached a few seconds."""
    now = time.monotonic()
    if now - _PAUSED_CACHE["at"] < max_age:
        return _PAUSED_CACHE["paused"]
    try:
        data = json.loads(_PAUSED_FILE.read_text(encoding="utf-8"))
        paused = isinstance(data, dict) and "Qwen" in data
    except (OSError, ValueError):
        paused = False
    _PAUSED_CACHE["at"] = now
    _PAUSED_CACHE["paused"] = paused
    return paused
