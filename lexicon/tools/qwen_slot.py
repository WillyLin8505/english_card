"""Card #1071 / issue #1580: a light lock for jobs that wait on Qwen (llama-server :8790), separate from heavy_lock.

heavy_lock is for jobs that eat CPU / memory (flutter test, full exports, qc --live). A translate run spends its minutes
waiting for the GPU, so it must not hold that lock. llama-server decodes `-np` requests at once (start_llm.py, default 4),
so up to QWEN_SLOTS (default 4) Qwen jobs run together, each holding one slot file lock until it exits (the OS drops it
with the process).

    python lexicon/tools/heavy_lock.py run -- python lexicon/tools/card828_translate.py ...   # auto-routed here
    from qwen_slot import slot; slot()
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heavy_lock  # noqa: E402

DIR = Path(__file__).resolve().parents[1] / "state"
SLOTS = max(1, int(os.environ.get("QWEN_SLOTS", "4")))
ENV = "QWEN_SLOT_HELD"
_FH = None

# scripts whose time goes into Qwen calls; `heavy_lock.py run` gives these a qwen slot instead of the heavy lock
QWEN_SCRIPTS = {"card828_translate.py", "card828_examples.py", "card437_relation_native.py",
                "card831_qwen_apply.py", "card832_run.py", "card832_batch.py",
                "card170_qwen_fill.py", "card344_qwen_fill.py", "card371_qwen_review.py",
                "card436_qwen_gloss_check.py", "card455_qwen_crop.py"}


def is_qwen_command(cmd: list[str]) -> bool:
    return any(Path(a.replace("\\", "/")).name in QWEN_SCRIPTS for a in cmd)


def slot(timeout_s: float = 3000.0) -> bool:
    """Take one of the QWEN_SLOTS slots, held until exit. False = gave up (the caller runs anyway)."""
    global _FH
    if os.environ.get(ENV) or _FH is not None:
        return True
    DIR.mkdir(parents=True, exist_ok=True)
    end = time.time() + timeout_s
    while True:
        for i in range(SLOTS):
            fh = open(DIR / f"qwen_slot{i}.lock", "a+")
            if heavy_lock._try(fh):
                _FH = fh
                os.environ[ENV] = "1"
                return True
            fh.close()
        if time.time() > end:
            return False
        time.sleep(5)
