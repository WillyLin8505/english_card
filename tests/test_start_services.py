import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('start_services', Path(__file__).resolve().parents[1] / 'start_services.py')
start_services = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start_services)


def test_app_restart_keeps_the_public_host(monkeypatch):
    # A restart without --public-host makes api.willylinai.com answer 403 (card #473).
    calls = []
    monkeypatch.setattr(start_services, 'ensure_service', lambda *args: calls.append(args) or 'started')
    start_services.main()
    app_calls = [args for args in calls if args[0] == 'serve_app.py']
    assert app_calls and app_calls[0][3] == ['--public-host', 'api.willylinai.com']
