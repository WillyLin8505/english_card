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


class GpuDuty:
    """Keeps the GPU idle part of the time (owner 11/06: 「GPU 已經百分百快爆了」).

    Any model call keeps the GPU at ~92-100 %. After a call that ran T seconds, no
    background call starts for T * (1 - duty) / duty seconds, so under steady
    import load the GPU is busy about ``duty`` of the time. Interactive calls (a
    learner's photo) never wait but still count. Cooperative: nothing is suspended
    (suspending llama-server preceded three VIDEO_TDR_FAILURE crashes)."""

    def __init__(self, duty, clock=time.monotonic, sleep=time.sleep):
        self.duty = min(1.0, max(0.05, float(duty)))
        self.clock, self.sleep = clock, sleep
        self.quiet_until = 0.0
        self.lock = threading.Lock()

    def wait_s(self):
        with self.lock:
            return max(0.0, self.quiet_until - self.clock())

    @contextlib.contextmanager
    def run(self, wait=True):
        while wait and self.duty < 1:
            delay = self.wait_s()
            if delay <= 0:
                break
            self.sleep(min(delay, 1.0))
        started = self.clock()
        try:
            yield
        finally:
            if self.duty < 1:
                ran = self.clock() - started
                with self.lock:
                    self.quiet_until = max(self.quiet_until,
                                           self.clock() + ran * (1 - self.duty) / self.duty)


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
