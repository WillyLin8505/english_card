"""P1 contracts over a pack: stubs out, photo-tag invariants, golden guard."""
from app import qc


def _pack():
    return {
        "lexemes": [
            {"id": 1, "lemma": "screen", "normalized": "screen", "pos": "noun", "status": "full",
             "cefr": "A2", "cefr_source": "cefr-j",
             "senses": [{"id": 10, "native": "螢幕", "priority": "main"},
                        {"id": 11, "native": "屏風", "priority": "low"}],
             "relations": [{"word": "screener", "lexeme_id": 99}]},
            {"id": 2, "lemma": "phone", "normalized": "phone", "pos": "noun", "status": "full",
             "cefr": "A1", "cefr_source": "cefr-j",
             "senses": [{"id": 20, "native": "電話", "priority": "main"}]},
            {"id": 3, "lemma": "screener", "normalized": "screener", "pos": "noun", "status": "stub",
             "cefr": "B1"},
            {"id": 4, "lemma": "screening", "normalized": "screening", "pos": "unknown",
             "status": "stub", "redirect_to": 1, "card": "screen"},
            {"id": 5, "lemma": "ghost", "normalized": "ghost", "pos": "noun", "status": "stub",
             "redirect_to": 3},  # points at a stub
        ],
        "redirects": {"4": 1, "5": 3},
        "catalog_images": [{
            "id": 71,
            "tags": [{"lexeme_id": 1, "sense_id": 10, "cefr": "A2"},
                     {"lexeme_id": 2, "sense_id": 20, "cefr": "B1"},  # level mismatch
                     {"lexeme_id": 4, "sense_id": 10, "cefr": "A2"}],  # on redirect
            "labels": [{"lexeme_id": 1, "cefr": "A2"}, {"lexeme_id": 2, "cefr": "B1"}],
        }],
    }


def test_validate_flags_stubs_and_photo_invariants():
    v = qc.validate(_pack())
    assert 3 in v["entry.stub_in_pack"] and 3 in v["entry.stub_has_cefr"]
    assert [71, 2] in v["photo_tag.level_differs_from_card"]
    assert [71, 4] in v["photo_tag.on_redirect"]
    assert [5, 3] in v["redirect.target_not_full"]


def test_strip_stubs_keeps_full_and_valid_pointers():
    pack = _pack()
    counts = qc.strip_stubs(pack)
    ids = {lx["id"] for lx in pack["lexemes"]}
    assert ids == {1, 2, 4}  # ghost pointer dropped; screener stub dropped
    assert pack["redirects"] == {"4": 1}
    assert pack["lexemes"][0]["relations"][0].get("lexeme_id") is None
    assert counts["kept_full"] == 2 and counts["kept_pointers"] == 1
    v = qc.validate(pack)
    assert "entry.stub_in_pack" not in v
    # A tag still naming a pointer id stays a violation: tags must name full entries.
    assert [71, 4] in v["photo_tag.on_redirect"]

def test_compare_detects_regression():
    before = {"metrics": {"v.entry.stub_in_pack": 10}, "golden": {"rates": {"word.present_full": 1.0}}}
    after = {"metrics": {"v.entry.stub_in_pack": 12}, "golden": {"rates": {"word.present_full": 0.9}}}
    bad = qc.compare(before, after)
    assert any("stub_in_pack" in x for x in bad) and any("word.present_full" in x for x in bad)
    assert qc.compare(before, before) == []

def test_validate_flags_latin_and_empty_native_on_any_sense():
    """問題回報 #187: every sense, not only the main one shown on the card."""
    pack = {"lexemes": [
        {"id": 1, "lemma": "table", "normalized": "table", "pos": "noun", "status": "full",
         "senses": [{"id": 10, "native": "桌子", "priority": "main"},
                    {"id": 11, "native": "背gammon遊戲"},
                    {"id": 12, "native": ""},
                    {"id": 13, "native": "家貓（Felis catus）"},   # 學名 note: exempt
                    {"id": 14, "native": "DNA 檢測"}]},            # whitelisted abbreviation
    ]}
    v = qc.validate(pack)
    assert v["sense.native_has_latin"] == [[1, "gammon"]]
    assert v["sense.native_empty"] == [1]


def test_compare_ignores_entries_added_during_a_run():
    before = {"metrics": {"full": 2, "v.sense.main_is_ai": 1}, "golden": {"rates": {}},
              "entry_ids": [1, 2], "v_ids": {"sense.main_is_ai": [1]}}
    after = {"metrics": {"full": 3, "v.sense.main_is_ai": 2}, "golden": {"rates": {}},
             "entry_ids": [1, 2, 3], "v_ids": {"sense.main_is_ai": [1, 3]}}
    assert qc.compare(before, after) == []  # entry 3 is new, not a regression
    after["v_ids"]["sense.main_is_ai"] = [1, 2]
    after["metrics"]["v.sense.main_is_ai"] = 2
    assert qc.compare(before, after)  # entry 2 got worse


def test_drop_unresolved_tags_and_labels():
    # Card #795 / Mac M386: le (200017) left the French pack, but both the
    # photo's tags and its point labels still pointed at it.
    pack = {"lexemes": [{"id": 1}],
            "catalog_images": [{"id": 9,
                                "tags": [{"lexeme_id": 1}, {"lexeme_id": 200017}],
                                "labels": [{"lexeme_id": 200017}, {"lexeme_id": 1}]}]}
    assert qc.drop_unresolved_tags(pack) == 2
    im = pack["catalog_images"][0]
    assert im["tags"] == [{"lexeme_id": 1}] and im["labels"] == [{"lexeme_id": 1}]
