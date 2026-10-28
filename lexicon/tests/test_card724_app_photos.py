import base64

import pytest
from fastapi import HTTPException

from app import app_photos, config

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def body(**kw):
    d = dict(photo_id="photo-1", image_b64=base64.b64encode(JPEG).decode(), device="iOS",
             labels=[{"word": "desk", "pos": "noun", "cefr": "A1"}, {"pos": "noun"}])
    d.update(kw)
    return app_photos.PhotoBody(**d)


@pytest.fixture(autouse=True)
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MEDIA", tmp_path)


def test_store_and_replace_labels():
    first = app_photos.store(body())
    assert [x["word"] for x in first["labels"]] == ["desk"]
    again = app_photos.store(body(labels=[{"word": "lamp"}]))
    assert again["id"] == first["id"] and again["first_uploaded_at"] == first["first_uploaded_at"]
    rows = app_photos.listing()
    assert len(rows) == 1 and rows[0]["labels"][0]["word"] == "lamp"


def test_rejects_non_image_and_bad_base64():
    with pytest.raises(HTTPException) as e:
        app_photos.store(body(image_b64=base64.b64encode(b"hello").decode()))
    assert e.value.status_code == 415
    with pytest.raises(HTTPException):
        app_photos.store(body(image_b64="***"))
