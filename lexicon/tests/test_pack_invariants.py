"""Invariants over the REAL pack (QUALITY P1). Set QC_PACK to a pack JSON
file or http URL (e.g. http://127.0.0.1:8123/api/lexicon); skipped otherwise.

These are the checks whose absence let #194 regress: they run over every
photo tag of the live pack, not over synthetic rows."""
import json
import os
import urllib.request
from pathlib import Path

import pytest

from app import qc

SRC = os.environ.get("QC_PACK")
pytestmark = pytest.mark.skipif(not SRC, reason="QC_PACK not set")

HARD_ZERO = (
    "entry.stub_in_pack", "entry.stub_has_cefr", "redirect.target_not_full",
    "relation.dangling_link", "photo_tag.on_redirect", "photo_tag.lexeme_not_full",
    "photo_tag.sense_missing", "photo_tag.level_differs_from_card",
    "photo_label.level_differs_from_card",
)


@pytest.fixture(scope="module")
def pack():
    if SRC.startswith("http"):
        with urllib.request.urlopen(SRC, timeout=600) as r:
            return json.load(r)
    return json.loads(Path(SRC).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def violations(pack):
    return qc.validate(pack)


@pytest.mark.parametrize("rule", HARD_ZERO)
def test_hard_invariant(violations, rule):
    assert not violations.get(rule), f"{rule}: {len(violations[rule])} e.g. {violations[rule][:5]}"


def test_photo_tags_show_chinese(violations, pack):
    tags = sum(len(im.get("tags") or []) for im in pack.get("catalog_images") or [])
    bad = len(violations.get("photo_tag.sense_without_chinese", []))
    assert bad <= max(20, tags // 200)  # 17 known words have no Chinese anywhere (#195)


def test_golden_known_photos(pack):
    res = qc.evaluate_golden(pack, qc.load_golden())
    assert res["rates"].get("photo.expected_sense") == 1.0, res["fails"].get("photo.expected_sense")
    assert res["rates"].get("word.present_full", 0) >= 0.99