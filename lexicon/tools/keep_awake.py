"""Keeps Windows from idle-sleeping while it runs (owner 10/22: 「保持網路 不要斷掉了」).

Same call the Claude app uses (SetThreadExecutionState); changes no power settings — a closed lid
or choosing Sleep still sleeps. watchdog.py starts it when it is not running.
"""
import ctypes
import time

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001

if __name__ == "__main__":
    while True:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        time.sleep(60)
