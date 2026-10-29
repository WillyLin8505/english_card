from tagging_server import PROMPT_VERSION, build_prompt, to_candidates


class FakeLexicon:
    def is_foreign(self, word):
        return word == "calendrier"

    def describe(self, word, lang="en"):
        return {"zipf": 4.0}

    def is_lexical_phrase(self, phrase):
        return phrase in {"butter knife", "traffic light"}


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


def test_english_candidates_reject_unattested_scene_descriptions():
    out = to_candidates([
        candidate("vehicle ahead", "vehicle visible farther along the road"),
        candidate("sunlit area", "bright sunlit part of the pavement"),
        candidate("lebara mobile", "words printed on a sign"),
        candidate("butter knife", "a butter knife on the table"),
        candidate("traffic light", "traffic light above the road"),
    ], FakeLexicon(), lang="en")

    assert [item["word"] for item in out] == ["butter knife", "traffic light"]


def test_prompt_explicitly_excludes_names_and_invalidates_old_cache():
    prompt = build_prompt("A2", "en", "zh-TW")
    assert "not company, product, model or person names" in prompt
    assert "Ignore words" in prompt and "logos" in prompt
    assert "safe=false" in prompt and "explicit adult nudity" in prompt
    assert PROMPT_VERSION == "photo-tags-context-v11-harder-level"


def test_cefr_prompt_lists_visible_objects_level_from_lexicon():
    from tagging_server import CEFR_PROMPT_VERSION, build_cefr_prompt
    """Decision 2 (QUALITY_SYSTEM_DESIGN.md): visible objects only; the level
    comes from the lexicon, so the prompt neither fills bands nor asks for l."""
    prompt = build_cefr_prompt("en", per_level=3)
    assert "EXACTLY" not in prompt and "AT LEAST" not in prompt
    assert "Do not invent CEFR levels" in prompt
    assert "clearly visible" in prompt
    assert "Mix parts of speech" in prompt
    assert "verbs" in prompt and "adjectives" in prompt and "adverbs" in prompt
    assert "- l:" not in prompt
    assert "safe=false" in prompt and "explicit adult nudity" in prompt
    assert "compact JSON keys" in prompt
    assert "precise, formal, literary or" in prompt
    assert CEFR_PROMPT_VERSION == "photo-tags-visible-v14-no-quotas"


def test_compact_cefr_candidates_decode_to_public_shape():
    out = to_candidates([{
        "w": "reflective", "p": "a", "l": "5",
        "e": "shine on metal", "x": 700, "y": 250,
    }])
    assert out[0]["word"] == "reflective"
    assert out[0]["pos"] == "adjective"
    assert out[0]["cefr"] is None
    assert out[0]["point"] == [0.7, 0.25]
    assert out[0]["box"] is None


def test_unsafe_image_is_rejected_before_candidates_are_cached(monkeypatch, tmp_path):
    import pytest
    import tagging_server as ts
    monkeypatch.setattr(ts, "CACHE_DIR", str(tmp_path))
    tagger = ts.Tagger("http://127.0.0.1:1", "test-model")
    monkeypatch.setattr(tagger, "_chat",
                        lambda *args, **kwargs: {"safe": False, "candidates": []})
    with pytest.raises(ts.UnsafeImage):
        tagger.candidates(b"not-an-image", "A1")
    assert list(tmp_path.iterdir()) == []


def test_stage_timings_split_queue_prep_model_and_llama_decode(monkeypatch, tmp_path):
    """問題回報 #229: each request reports where its seconds went; a cache hit makes no model call."""
    import io
    import tagging_server as ts
    from repetition_guard import read_cefr_stream
    monkeypatch.setattr(ts, "CACHE_DIR", str(tmp_path))
    tagger = ts.Tagger("http://127.0.0.1:1", "test-model")

    def fake_backend(*args, **kwargs):
        ts.note_llama_timings({"prompt_ms": 410.4, "predicted_ms": 7200.6,
                               "prompt_n": 300, "predicted_n": 180})
        return {"safe": True, "candidates": [{"word": "cup", "pos": "noun"}]}

    monkeypatch.setattr(tagger, "_chat_backend", fake_backend)
    stages = ts.stages_reset()
    tagger.candidates(b"not-an-image", "A1")
    assert stages["modelCalls"] == 1 and stages["decodeMs"] == 7201
    assert stages["promptTokens"] == 300 and stages["decodeTokens"] == 180
    assert {"queueMs", "prepMs", "modelMs"} <= set(stages)
    again = ts.stages_reset()
    tagger.candidates(b"not-an-image", "A1")
    assert again["modelCalls"] == 0

    seen = []
    stream = io.BytesIO(b'data: {"choices":[{"delta":{"content":"{}"}}]}\n'
                        b'data: {"choices":[],"timings":{"predicted_ms":5}}\n'
                        b'data: [DONE]\n')
    assert read_cefr_stream(stream, on_timings=seen.append) == "{}"
    assert seen == [{"predicted_ms": 5}]


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



def test_cap_cefr_beginner_bands_drops_overflow():
    from tagging_server import cap_cefr_beginner_bands, cefr_band_counts, merge_cefr_topup

    def item(word, cefr, pos="noun"):
        return {"word": word, "lemma": word, "pos": pos, "cefr": cefr,
                "modelLevel": cefr, "evidence": word, "point": [0.5, 0.5],
                "box": None, "visualConfidence": 0.7, "usefulness": 0.5,
                "inferred": False, "meaning": ""}

    raw = [
        item("cup", "A1"), item("plate", "A1"), item("bowl", "A1"),
        item("mug", "A1"),  # overflow A1
        item("saucer", "A2"), item("napkin", "A2"), item("tray", "A2"),
        item("ladle", "A2"),  # overflow A2
        item("simmer", "B2", pos="verb"),
        item("ornate", "C1", pos="adjective"),
    ]
    out = cap_cefr_beginner_bands(raw, beginner_max=3)
    counts = cefr_band_counts(out)
    assert counts["A1"] == 3
    assert counts["A2"] == 3
    assert counts["B2"] == 1 and counts["C1"] == 1
    assert "mug" not in {x["word"] for x in out}
    assert "ladle" not in {x["word"] for x in out}
    assert {x["word"] for x in out} >= {"simmer", "ornate"}

    # Top-up must not push beginners past the cap either.
    existing = [item("cup", "A1"), item("plate", "A1"), item("bowl", "A1")]
    extra = [item("mug", "A1"), item("whisk", "B2", pos="noun")]
    merged = merge_cefr_topup(existing, extra, per_level=3, beginner_max=3)
    assert cefr_band_counts(merged)["A1"] == 3
    assert "mug" not in {x["word"] for x in merged}
    assert "whisk" in {x["word"] for x in merged}


def test_translation_bundle_keeps_each_items_task():
    from tagging_server import translate

    class FakeTagger:
        def __init__(self):
            self.prompt = ""

        def _chat(self, prompt, schema, **kwargs):
            self.prompt = prompt
            return {"items": [{"id": "a", "text": "長椅"},
                              {"id": "b", "text": "她坐下。"}]}

    tagger = FakeTagger()
    result = translate(tagger, {
        "lang": "en", "native": "zh-TW", "kind": "bundle",
        "items": [
            {"id": "a", "task": "gloss", "text": "A long seat."},
            {"id": "b", "task": "sentence", "text": "She sat down."},
        ],
    })

    assert [item["id"] for item in result["items"]] == ["a", "b"]
    assert '"task": "gloss"' in tagger.prompt
    assert '"task": "sentence"' in tagger.prompt


def test_translation_retries_english_echoes_one_item_at_a_time():
    from tagging_server import translate

    class FakeTagger:
        def __init__(self):
            self.calls = 0

        def _chat(self, prompt, schema, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"items": [
                    {"id": "a", "text": "Swallows build their nests from clay."},
                    {"id": "b", "text": "The bowl is made of clay."},
                ]}
            if '"id": "a"' in prompt:
                return {"items": [{"id": "a", "text": "燕子用黏土築巢。"}]}
            return {"items": [{"id": "b", "text": "這個碗是陶土製成的。"}]}

    tagger = FakeTagger()
    result = translate(tagger, {
        "lang": "en", "native": "zh-TW", "kind": "sentence",
        "items": [
            {"id": "a", "text": "Swallows build their nests from clay."},
            {"id": "b", "text": "The bowl is made of clay."},
        ],
    })

    assert tagger.calls == 3
    assert [item["text"] for item in result["items"]] == [
        "燕子用黏土築巢。", "這個碗是陶土製成的。"]


def test_inference_slots_limit_concurrency_and_queue_same_key(monkeypatch, tmp_path):
    import threading
    import time
    import tagging_server

    monkeypatch.setattr(tagging_server, "INFERENCE_PARALLEL", 2)
    monkeypatch.setattr(tagging_server, "CACHE_DIR", str(tmp_path))
    tagger = tagging_server.Tagger("http://127.0.0.1:1", "test-model")
    running, peak, same, same_peak = [0], [0], [0], [0]
    guard = threading.Lock()

    def work(key):
        with tagger._inference(key):
            with guard:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
                if key == "same":
                    same[0] += 1
                    same_peak[0] = max(same_peak[0], same[0])
            time.sleep(0.05)
            with guard:
                running[0] -= 1
                if key == "same":
                    same[0] -= 1

    threads = [threading.Thread(target=work, args=(key,))
               for key in (None, None, None, None, "same", "same")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2
    assert same_peak[0] == 1, "identical requests wait for the cached reply"
    assert tagger._key_locks == {}


def test_compact_grammar_leaves_no_room_for_whitespace():
    import tagging_server as ts
    """llama-server gets a grammar for the CEFR label reply with every key in
    schema order and no spaces; a schema with optional keys keeps json_schema."""
    grammar = ts.compact_grammar(ts.CEFR_CANDIDATE_SCHEMA)
    assert grammar.startswith('root ::= reply\n')
    assert 'reply ::= "{\\"safe\\":" ("true" | "false") ",\\"candidates\\":"' in grammar
    assert '"{\\"w\\":" string ",\\"p\\":" ("\\"n\\""' in grammar
    assert '" "' not in grammar and "[ \t" not in grammar
    assert ts.compact_grammar({'type': 'object', 'properties': {'a': {'type': 'string'}},
                               'required': []}) is None


def test_level_filter_drops_labels_below_one_band_under_the_level():
    # Card #657: pedestrian is B2 in CEFR-J and propulsion is a frequency estimate of B2
    # (zipf 3.6); neither may reach a C2 learner, and no easier word is filled in.
    from tagging_server import finish_candidates
    items = [{'word': 'pedestrian', 'zipf': 3.71}, {'word': 'propulsion', 'zipf': 3.6},
             {'word': 'iridescent', 'zipf': 2.8}, {'word': 'bright', 'zipf': 4.6}]
    out = [i['word'] for i in finish_candidates(items, 'C2', 'en', None)]
    assert out == ['iridescent']
    out = [i['word'] for i in finish_candidates([dict(i) for i in items], 'B1', 'en', None)]
    assert 'pedestrian' in out and 'iridescent' in out and 'bright' not in out
    assert finish_candidates([{'word': 'bright', 'zipf': 4.6}], 'C2', 'en', None) == []


def test_harder_returns_rarest_six_with_band_attached():
    from tagging_server import finish_candidates
    items = [{'word': f'w{n}', 'zipf': 3.1 + n / 10} for n in range(8)]
    out = finish_candidates(items, 'B1', 'en', 'harder')
    assert len(out) == 6 and out[0]['cefr'] in ('B1', 'B2', 'C1', 'C2')
    assert all(i['cefrSource'] == 'estimate' for i in out)


def test_word_cefr_uses_the_list_before_frequency():
    from tagging_server import word_cefr, cefr_list_words
    assert word_cefr('pedestrian', 2.0) == ('B2', 'list')
    assert word_cefr('prominent', None) == ('B1', 'list')
    assert word_cefr('propulsion', 3.6) == ('B2', 'estimate')
    # Card #685: no zipf given -> looked up, so no unlisted word stays band-less.
    assert word_cefr('stroll', None) == ('B2', 'estimate')
    assert word_cefr('traffic light', None)[0] is not None
    assert 'abortion' in cefr_list_words()  # Oxford extra is merged in


def test_easier_focus_skips_the_level_filter():
    from tagging_server import finish_candidates
    items = [{'word': 'tree', 'zipf': 5.5}]
    assert finish_candidates(items, 'C2', 'en', 'easier')[0]['cefr'] == 'A1'


def test_level_filter_drops_unlisted_easy_words_without_zipf():
    from tagging_server import finish_candidates
    items = [{'word': w} for w in ('stroll', 'dwell', 'congested', 'conspire')]
    assert [i['word'] for i in finish_candidates(items, 'C2', 'en', None)] == ['congested', 'conspire']


def test_french_labels_resolve_against_pack_index():
    from tagging_server import pack_resolve
    index = {"words": {"arbre": ["noun"], "lit": ["noun"], "marcher": ["verb"]},
             "forms": {"arbres": "arbre"}}
    assert pack_resolve("arbres", "noun", index) == ("arbre", "noun")
    assert pack_resolve("lit", "adjective", index) == ("lit", "noun")
    assert pack_resolve("apple", "noun", index) is None
    assert "Every word must be a real French word" in build_prompt("A2", "fr", "en")
