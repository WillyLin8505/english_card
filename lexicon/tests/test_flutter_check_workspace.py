from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from flutter_check_workspace import check_workspace


def test_check_workspace_includes_privacy_fixture_without_local_credentials(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "docs").mkdir()
    policy = "<h2>Privacy</h2><p>Test policy</p>"
    (tmp_path / "docs/privacy.html").write_text(policy, encoding="utf-8")
    (tmp_path / "app/pubspec.yaml").write_text("name: test_app", encoding="utf-8")
    # Synthetic sentinel only: never inspect the real local configuration.
    (tmp_path / "app/tagging.local.json").write_text("{}", encoding="utf-8")
    with check_workspace(tmp_path) as app:
        assert (app.parent / "docs/privacy.html").read_text(encoding="utf-8") == policy
        assert (app / "pubspec.yaml").is_file()
        assert not (app / "tagging.local.json").exists()
