"""問題回報 #188: a manual override bypasses adapters.base.validate()
(pipeline.py short-circuits to the override as soon as one exists), so
put_override must reject ARPAbet posing as IPA itself. No DB needed: the
guard runs before any session use."""
import pytest
from fastapi import HTTPException

from app.main import OverrideBody, put_override


def test_rejects_bare_arpabet_as_ipa():
    with pytest.raises(HTTPException) as e:
        put_override("en", "zh-TW", "steep", "ipa", OverrideBody(items=[{"ipa": "S T IY1 P"}]), s=None)
    assert e.value.status_code == 422


def test_rejects_slash_wrapped_arpabet_as_ipa():
    with pytest.raises(HTTPException) as e:
        put_override("en", "zh-TW", "steep", "ipa", OverrideBody(items=[{"ipa": "/S T IY1 P/"}]), s=None)
    assert e.value.status_code == 422
    assert "ARPAbet" in e.value.detail


def test_rejects_ipa_shaped_value_in_phonemes_field():
    with pytest.raises(HTTPException) as e:
        put_override("en", "zh-TW", "steep", "phonemes", OverrideBody(items=[{"phonemes": "/stiːp/"}]), s=None)
    assert e.value.status_code == 422
