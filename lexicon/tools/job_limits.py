"""Card #731 / issue #872: put a dispatched CLI (and every child it starts) in a Windows Job Object with a
memory cap and BelowNormal priority. Services are never passed in. The job keeps its limits after the
launcher exits (no kill-on-close). Best effort: returns False instead of raising."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

JOB_OBJECT_LIMIT_PRIORITY_CLASS = 0x20
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
BELOW_NORMAL = 0x4000
PROCESS_SET_QUOTA, PROCESS_TERMINATE = 0x0100, 0x0001


class _Basic(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _Io(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]


class _Ext(ctypes.Structure):
    _fields_ = [("Basic", _Basic), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def build_limits(mem_gb: float) -> _Ext:
    e = _Ext()
    e.Basic.LimitFlags = JOB_OBJECT_LIMIT_PRIORITY_CLASS | JOB_OBJECT_LIMIT_JOB_MEMORY
    e.Basic.PriorityClass = BELOW_NORMAL
    e.JobMemoryLimit = int(mem_gb * 1024 ** 3)
    return e


def assign(pid: int, mem_gb: float = 6.0) -> bool:
    if os.name != "nt":
        return False
    try:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateJobObjectW.restype = wintypes.HANDLE
        k.OpenProcess.restype = wintypes.HANDLE
        job = k.CreateJobObjectW(None, None)
        if not job:
            return False
        e = build_limits(mem_gb)
        if not k.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(e), ctypes.sizeof(e)):
            return False
        h = k.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not h:
            return False
        try:
            return bool(k.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(h)))
        finally:
            k.CloseHandle(wintypes.HANDLE(h))
    except Exception:  # noqa: BLE001
        return False
