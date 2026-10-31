import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tagger"))
sys.path.insert(0, str(ROOT / "lexicon" / "tools"))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_free_port():
    import tagging_server
    assert tagging_server.probe_port_owner("127.0.0.1", _free_port()) == "free"


def test_other_program_detected():
    import tagging_server
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(5)
    try:
        assert tagging_server.probe_port_owner("127.0.0.1", s.getsockname()[1]) == "other"
    finally:
        s.close()


def test_exclusive_bind_refuses_second_server():
    import tagging_server
    from http.server import BaseHTTPRequestHandler
    port = _free_port()
    a = tagging_server.ExclusiveThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
    try:
        try:
            b = tagging_server.ExclusiveThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
        except OSError:
            return
        b.server_close()
        raise AssertionError("second bind succeeded")
    finally:
        a.server_close()
