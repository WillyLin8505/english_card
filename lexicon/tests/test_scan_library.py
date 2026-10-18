"""Card #161: scan_library groups a small fake pack and stays read-only."""
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import scan_library as scan  # noqa: E402


def _pack():
    images = [{"path": "/a.jpg", "role": "representative", "tags": [{"word": "other"}]}]
    return {
        "lexemes": [
            {"id": 1, "lemma": "walked", "normalized": "walked", "pos": "verb", "status": "full",
             "cefr": "B1", "cefr_source": "frequency_estimate", "usage_rank": 1,
             "senses": [{"id": 11, "definition": "simple past of walk", "native": "走了",
                         "priority": "main"}],
             "examples": [{"text": "She walked home."}],
             "pronunciations": [{"kind": "ipa", "value": "wɔkt", "audio": "/a.mp3"}],
             "forms": [{"normalized": "walked"}]},
            {"id": 2, "lemma": "row", "normalized": "row", "pos": "verb", "status": "full",
             "cefr": "A2", "cefr_source": "cefr-j", "usage_rank": 0,
             "senses": [
                 {"id": 21, "definition": "simple past of row", "native": "", "priority": "low",
                  "labels": ["archaic"]},
                 {"id": 23, "definition": "an old sense", "native": "舊列", "priority": "low",
                  "images": images},
                 {"id": 22, "definition": "to propel a boat", "native": "划船", "priority": "main"},
             ],
             "examples": [{"text": "row"}],
             "pronunciations": [{"kind": "ipa", "value": "roʊ"}]},
            {"id": 3, "lemma": "pot", "normalized": "pot", "pos": "noun", "status": "full",
             "cefr": "A1", "cefr_source": "cefr-j", "usage_rank": 0,
             "senses": [{"id": 31, "definition": "a container", "native": "鍋", "priority": "main"}],
             "examples": [{"text": "Tom has a pot."}],
             "pronunciations": [{"kind": "audio", "value": "", "audio": "/p.mp3"}]},
            {"id": 4, "lemma": "potted", "normalized": "potted", "pos": "adj", "status": "full",
             "cefr": "C2", "cefr_source": "frequency_estimate", "usage_rank": 0,
             "senses": [{"id": 41, "definition": "placed in a pot", "native": "盆栽的 Pot",
                         "priority": "main", "native_ai": True,
                         "images": [{"path": str(i)} for i in range(15)]}],
             "examples": [{"text": "Ziri bought one"}],
             "pronunciations": [{"kind": "ipa", "value": "S T IY1"}]},
            {"id": 5, "lemma": "frail", "normalized": "frail", "pos": "noun", "status": "full",
             "cefr": "C1", "cefr_source": "quality_rule", "usage_rank": 0,
             "senses": [{"id": 51, "definition": "a basket", "native": "籃子", "priority": "main",
                         "labels": ["obsolete", "rare"]}],
             "relations": [{"word": "crap", "relation": "related"}],
             "pronunciations": [{"kind": "ipa", "value": "freɪl", "audio": "/f.mp3"}],
             "examples": [{"text": "The frail one said fuck."}]},
            {"id": 6, "lemma": "frail", "normalized": "frail", "pos": "adj", "status": "full",
             "cefr": "B1", "cefr_source": "octanove", "usage_rank": 1,
             "senses": [{"id": 61, "definition": "weak", "native": "脆弱", "priority": "main"}],
             "pronunciations": [{"kind": "ipa", "value": "freɪl", "audio": "/f.mp3"}],
             "examples": []},
            {"id": 7, "lemma": "gone", "normalized": "gone", "pos": "verb", "status": "stub",
             "cefr": "A1", "senses": []},
        ],
        "catalog_images": [
            {"id": 71, "tags": [
                {"lexeme_id": 1, "sense_id": 11},
                {"lexeme_id": 4, "sense_id": 41, "sense_fallback": True},
                {"lexeme_id": 2, "sense_id": 21},
                {"lexeme_id": 2, "sense_id": 23},
            ], "labels": [
                {"word": "surface", "cefr": "A1"},
                {"word": "rock", "cefr": "A2"},
            ]},
            {"id": 72, "tags": [{"lexeme_id": 5, "sense_id": 51}],
             "labels": [{"word": "stone"}, {"word": "rock"}]},
        ],
    }


def _n(report, group, check):
    return report["groups"][group]["checks"][check]["n"]


def test_groups_count_the_fake_pack():
    report = scan.scan_pack(_pack())
    assert _n(report, "A", "inflection_only_leveled") == 1
    assert _n(report, "A", "inflection_only_leveled_on_photos") == 1
    assert _n(report, "A", "mixed_formof_plus_real_senses") == 1
    assert _n(report, "A", "inflection_only_full") == 1
    assert _n(report, "B", "full_cefr_estimated") == 3  # walked, potted, frail noun
    assert _n(report, "B", "est_C1C2_on_photos") == 2  # potted C2, frail noun C1
    assert _n(report, "B", "est_C1C2_nouns_on_photos") == 1
    assert _n(report, "B", "estimate_2plus_above_listed_base") == 1
    assert _n(report, "C", "main_usage_all_senses_archaic_rare") == 1
    assert _n(report, "C", "photo_senses_nonmain_with_images") == 1
    assert _n(report, "C", "photo_image_rows_on_low") == 1
    assert _n(report, "C", "tags_sense_fallback") == 1
    assert _n(report, "C", "photo_tag_sense_low_priority") == 1
    assert _n(report, "D", "main_sense_empty") == 1
    assert _n(report, "D", "senses_native_empty") == 1
    assert _n(report, "D", "native_has_latin_letters") == 1
    assert _n(report, "D", "main_sense_ai") == 1
    assert _n(report, "D", "photo_tag_sense_without_chinese") == 1
    assert _n(report, "E", "examples_not_sentence") == 2  # "row" and "Ziri bought one"
    assert _n(report, "E", "examples_odd_tatoeba_names") == 1
    assert _n(report, "E", "examples_missing_lemma") == 1  # "Tom has a pot."
    assert _n(report, "E", "full_without_examples") == 1
    assert _n(report, "E", "examples_profanity") == 1
    assert _n(report, "E", "relations_profanity") == 1
    assert _n(report, "F", "catalog_images") == 2
    assert _n(report, "F", "images_lt3_labels") == 2
    assert _n(report, "F", "images_le2_levels") == 2
    assert _n(report, "F", "generic_tag_uses") == 1
    assert _n(report, "F", "images_synonym_pairs") == 1
    assert _n(report, "G", "lexemes_ge15_images") == 1
    assert _n(report, "G", "adj_ge15_images") == 1
    assert _n(report, "G", "representative_missing_word") == 1
    assert _n(report, "H", "full_without_ipa") == 1  # pot has only kind=audio
    assert _n(report, "H", "ipa_is_arpabet") == 1
    assert _n(report, "H", "full_without_audio_path") == 2  # row, potted
    assert report["pack"]["full"] == 6
    samples = report["groups"]["B"]["checks"]["estimate_2plus_above_listed_base"]["samples"]
    assert samples == ["potted(C2) base pot"]


def test_sample_cap_and_delta_and_group_filter():
    report = scan.scan_pack(_pack())
    capped = scan._check(40, [f"w{i}" for i in range(40)])
    assert capped["n"] == 40 and len(capped["samples"]) == scan.SAMPLE_MAX
    previous = {"groups": {"A": {"checks": {"inflection_only_leveled": {"n": 5}}}}}
    diff = scan.delta_against(report, previous)
    assert diff["A.inflection_only_leveled"] == {"n": 1, "prev": 5, "diff": -4}
    assert diff["B.full_cefr_estimated"]["prev"] is None
    only = scan.select_groups(report, ["d"])
    assert list(only["groups"]) == ["D"]


def test_scientific_name_is_not_a_latin_issue():
    pack = _pack()
    pack["lexemes"][0]["senses"][0]["native"] = "家貓（Felis catus）"
    report = scan.scan_pack(pack)
    assert _n(report, "D", "native_has_latin_letters") == 2
    assert _n(report, "D", "native_latin_issue") == 1


def test_cli_help_and_pack_file(tmp_path):
    with pytest.raises(SystemExit) as caught:
        scan.main(["--help"])
    assert caught.value.code == 0
    path = tmp_path / "pack.json"
    path.write_text(json.dumps(_pack()), encoding="utf-8")
    out = tmp_path / "scan"
    assert scan.main(["--pack", str(path), "--out", str(out), "--only", "A"]) == 0
    stamped = list(out.glob("scan-*.json"))
    assert len(stamped) == 1
    body = json.loads(stamped[0].read_text(encoding="utf-8"))
    assert list(body["groups"]) == ["A"]
    assert not (out / "latest.json").exists()
    assert scan.main(["--pack", str(path), "--out", str(out)]) == 0
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert latest["read_only"] is True and "H" in latest["groups"]
    assert latest["delta"]["A.inflection_only_leveled"]["prev"] is None
