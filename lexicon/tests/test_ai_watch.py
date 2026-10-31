"""Owner 10/31: AI work stays under 80 % of the PC (lexicon/tools/ai_watch.py)."""
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


def test_gpu_rests_when_busy_for_a_while_or_too_hot():
    assert w.gpu_should_rest(95, 70, None, 100.0) == (False, 100.0)
    assert w.gpu_should_rest(95, 70, 100.0, 159.0) == (False, 100.0)
    assert w.gpu_should_rest(95, 70, 100.0, 160.0) == (True, 100.0)
    assert w.gpu_should_rest(40, 70, 100.0, 160.0) == (False, None)
    assert w.gpu_should_rest(40, 85, None, 100.0) == (True, None)
    assert w.gpu_should_rest(None, None, 100.0, 160.0) == (False, None)


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
