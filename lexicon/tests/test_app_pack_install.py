"""install() copies media but never ships a raw export as the app pack (問題回報 #405)."""
import json

from app.app_pack import install


def test_install_keeps_the_bundled_pack(tmp_path):
    release = tmp_path / "language-data-en-zh-TW-1"
    (release / "media" / "audio" / "en").mkdir(parents=True)
    (release / f"{release.name}.json").write_text('{"lexemes": []}', encoding="utf-8")
    (release / "manifest.json").write_text("{}", encoding="utf-8")
    (release / "media" / "audio" / "en" / "a.mp3").write_bytes(b"x")
    assets = tmp_path / "assets"
    assets.mkdir()
    bundled = {"bundled": True, "lexemes": [{"id": 1}]}
    (assets / "en-zh-TW.json").write_text(json.dumps(bundled), encoding="utf-8")

    out = install(release, "en", "zh-TW", app_assets=assets)

    assert json.loads((assets / "en-zh-TW.json").read_text(encoding="utf-8")) == bundled
    assert not (assets / "en-zh-TW.manifest.json").exists()
    assert (assets / "media" / "audio" / "en" / "a.mp3").read_bytes() == b"x"
    assert out["media_copied"] == 1 and "card268_bundle_pack.py" in out["bundle"]
