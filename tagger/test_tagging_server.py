from tagging_server import PROMPT_VERSION, build_prompt, to_candidates


class FakeLexicon:
    def is_foreign(self, word):
        return word == "calendrier"

    def describe(self, word, lang="en"):
        return {"zipf": 4.0}


def candidate(word, evidence):
    return {
        "word": word,
        "pos": "noun",
        "evidence": evidence,
        "point": [500, 500],
        "box": [400, 400, 600, 600],
    }


def test_english_candidates_reject_foreign_words_and_brand_names():
    out = to_candidates([
        candidate("calendar", "calendar hanging on the wall"),
        candidate("calendrier", "word on the calendar"),
        candidate("dell", "Dell logo on the laptop"),
        candidate("logo", "logo visible on the laptop"),
        candidate("cap", "gray cap with logo"),
    ], FakeLexicon(), lang="en")

    assert [item["word"] for item in out] == ["calendar", "logo", "cap"]


def test_prompt_explicitly_excludes_names_and_invalidates_old_cache():
    prompt = build_prompt("A2", "en", "zh-TW")
    assert "not company, product, model or person names" in prompt
    assert "Ignore words" in prompt and "logos" in prompt
    assert PROMPT_VERSION == "photo-tags-context-v5"


def test_cefr_prompt_requires_at_least_per_level():
    from tagging_server import CEFR_PROMPT_VERSION, build_cefr_prompt
    prompt = build_cefr_prompt("en", per_level=3)
    assert "AT LEAST 3" in prompt
    assert "Every band must meet the minimum" in prompt
    assert "return fewer for that band" not in prompt
    assert CEFR_PROMPT_VERSION == "photo-tags-cefr-bands-v3"


def test_merge_cefr_topup_fills_short_bands_without_inventing():
    from tagging_server import merge_cefr_topup, cefr_band_counts, short_cefr_bands

    def item(word, cefr):
        return {"word": word, "lemma": word, "pos": "noun", "cefr": cefr,
                "modelLevel": cefr, "evidence": word, "point": [0.5, 0.5],
                "box": None, "visualConfidence": 0.7, "usefulness": 0.5,
                "inferred": False, "meaning": ""}

    existing = [
        item("cup", "A1"), item("plate", "A1"),
        item("saucer", "A2"),
    ]
    extra = [
        item("cup", "A1"),  # duplicate ignored
        item("mug", "A1"),  # fills A1 to 3
        item("bowl", "A2"), item("fork", "A2"),  # fills A2 to 3
        item("teapot", "B1"),  # new band ok while short
        item("ladle", "A1"),  # A1 already at 3 after mug — ignored later
    ]
    # After mug, A1 has 3; ladle should be skipped by merge once A1 full.
    out = merge_cefr_topup(existing, extra, per_level=3)
    counts = cefr_band_counts(out)
    assert counts["A1"] == 3
    assert counts["A2"] == 3
    assert counts["B1"] == 1
    assert short_cefr_bands(out, 3)  # other bands still short
    assert "ladle" not in {x["word"] for x in out}

