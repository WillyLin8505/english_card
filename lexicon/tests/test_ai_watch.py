"""Owner 10/31, 11/01: the PC stays under 50 % CPU and GPU (lexicon/tools/ai_watch.py)."""
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ai_watch as w  # noqa: E402


def test_what_joins_the_job():
    assert w.is_ai_process("python.exe", r"C:\py\python.exe", r"python worker\worker.py --lane text")
    assert w.is_ai_process("llama-server.exe", "x", "--port 8790")
    assert w.is_ai_process("claude.exe", r"C:\Users\u\.local\bin\claude.exe", "claude -p")
    assert not w.is_ai_process("python.exe", "x", r"python D:\x\serve_app.py --port 8123")
    assert not w.is_ai_process("python.exe", "x", "python -m uvicorn app.main:app --port 8770")
    assert not w.is_ai_process("claude.exe", r"C:\Users\u\AppData\Local\AnthropicClaude\app-4\claude.exe", "")
    assert not w.is_ai_process("chrome.exe", "x", "")


def test_cpu_caps_shrink_near_the_limit_and_recover_slowly():
    assert w.cpu_scale(60, 1.0) == 0.7
    assert w.cpu_scale(40, 0.7) == 0.49
    assert w.cpu_scale(90, 0.11) == w.MIN_SCALE
    assert w.cpu_scale(35, 0.5) == 0.5
    assert w.cpu_scale(20, 0.5) == 0.6
    assert w.cpu_scale(20, 1.0) == 1.0
    assert w.cpu_scale(None, 0.5) == 0.5


def test_all_ai_caps_together_stay_within_the_budget():
    w.scale = 1.0
    for clis in (1, 2, 5, 11):
        assert w.shared_cap() + w.tree_cap(clis) * clis <= w.AI_BUDGET_PCT + 0.01 * clis
    assert w.tree_cap(1) == w.TREE_CPU_PCT
    assert w.tree_cap(49) == w.TREE_MIN_PCT  # more CLIs than the budget holds: cpu_scale takes over
    w.scale = 0.5
    assert w.shared_cap() == 11.0
    w.scale = 1.0


def test_gpu_runs_in_bursts_while_busy():
    assert w.gpu_pacing(95, False)
    assert w.gpu_pacing(45, False)
    assert not w.gpu_pacing(35, False)
    assert w.gpu_pacing(35, True)  # bursts hold GPU here, that is not idle
    assert not w.gpu_pacing(15, True)
    assert w.gpu_pacing(None, True)


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows only")
def test_windows_enforces_the_job_limits():
    w._setup_api()
    job = w.create_job(None, 2, 300 * 2**20)  # 2 % CPU, 300 MB
    hold = "import time; time.sleep(1.5); "
    big = subprocess.Popen([sys.executable, "-c", hold + "b = bytearray(600 * 2**20); print('allocated')"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert w.assign(job, big.pid)
    out, err = big.communicate(timeout=60)
    assert "allocated" not in out and "MemoryError" in err

    spin = subprocess.Popen([sys.executable, "-c", hold + "\nwhile True: pass"])
    try:
        assert w.assign(job, spin.pid)
        p = psutil.Process(spin.pid)
        time.sleep(1.6)
        before, t0 = sum(p.cpu_times()[:2]), time.time()
        time.sleep(3)
        used = (sum(p.cpu_times()[:2]) - before) / (time.time() - t0)
        # 2 % of all cores, on one spinning core an uncapped run would use 1.0 here.
        assert used < 2 * 0.02 * psutil.cpu_count()
    finally:
        spin.kill()
