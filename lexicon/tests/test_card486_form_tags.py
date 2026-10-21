"""Card #486 (問題回報 #488): photo tags never sit on a bare inflection entry."""

from app import quality as q


def _lx(i, word, pos, definition, cefr, **extra):
    return {"id": i, "normalized": word, "lemma": word, "pos": pos, "status": "full", "cefr": cefr,
            "senses": [{"id": i * 10, "native": "x", "priority": "main", "definition": definition}], **extra}


def _pack(tags):
    lexemes = [_lx(1, "gaze", "verb", "To stare.", "C1"),
               _lx(2, "gazing", "verb", "present participle and gerund of gaze", None),
               _lx(3, "railing", "verb", "present participle of rail", None),
               _lx(4, "railing", "noun", "A fence.", "B2"),
               _lx(5, "rail", "noun", "A bar.", "B1")]
    image = {"id": 1, "tags": tags, "labels": [{"word": "railing", "pos": "verb", "lexeme_id": 3}]}
    return {"lexemes": lexemes, "redirects": {}, "catalog_images": [image]}


def test_form_only_tag_moves_to_same_spelling_entry_then_base():
    pack = _pack([{"lexeme_id": 3, "sense_id": 30}, {"lexeme_id": 2, "sense_id": 20}])
    q.fix_catalog_senses(pack)
    a, b = pack["catalog_images"][0]["tags"]
    assert (a["lexeme_id"], a["cefr"], a["lexeme_id_before"]) == (4, "B2", 3)
    assert (b["lexeme_id"], b["cefr"]) == (1, "C1")
    assert pack["catalog_images"][0]["labels"][0]["lexeme_id"] == 4
    assert q.fix_catalog_senses(pack) == 0  # idempotent


def test_form_tag_dropped_when_base_already_on_photo():
    pack = _pack([{"lexeme_id": 1, "sense_id": 10}, {"lexeme_id": 2, "sense_id": 20}])
    q.fix_catalog_senses(pack)
    assert [t["lexeme_id"] for t in pack["catalog_images"][0]["tags"]] == [1]
