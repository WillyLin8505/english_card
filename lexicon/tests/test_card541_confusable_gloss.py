"""Card 541 / 問題回報 #581: 「容易混淆的字」 Chinese comes from the other word's main meaning."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.app_pack import fix_confusable_glosses  # noqa: E402


def lex(id_, lemma, pos, usage_rank, senses, relations=(), status="full"):
    return {"id": id_, "lemma": lemma, "normalized": lemma, "pos": pos, "status": status,
            "usage_rank": usage_rank, "senses": [{"native": n, "native_ai": False} for n in senses],
            "relations": list(relations)}


def rel(word, lexeme_id, native, relation="near_homophones"):
    return {"relation": relation, "word": word, "lexeme_id": lexeme_id, "native": native,
            "native_ai": False, "hide_by_default": False, "detail": {}}


def test_rare_gloss_replaced_by_other_word_main_meaning():
    page = lex(1, "page", "noun", 0, ["頁"], [rel("pale", 2, "柵欄")])
    pale = lex(2, "pale", "adj", 0, ["蒼白的", "淡色的", "微弱的"])
    fix_confusable_glosses({"lexemes": [page, pale]})
    assert page["relations"][0]["native"] == "蒼白的"


def test_main_meaning_kept():
    page = lex(1, "page", "noun", 0, ["頁"], [rel("pale", 2, "蒼白")])
    pale = lex(2, "pale", "adj", 0, ["蒼白的", "淡色的"])
    assert fix_confusable_glosses({"lexemes": [page, pale]}) == 0
    assert page["relations"][0]["native"] == "蒼白"


def test_same_as_headword_hidden():
    page = lex(1, "page", "noun", 0, ["頁"], [rel("sheet", 2, "柵欄")])
    sheet = lex(2, "sheet", "noun", 0, ["頁面", "床單"])
    fix_confusable_glosses({"lexemes": [page, sheet]})
    assert page["relations"][0]["native"] == "頁面"
    assert page["relations"][0]["hide_by_default"] is False
    page2 = lex(1, "page", "noun", 0, ["頁面"], [rel("sheet", 2, "柵欄")])
    fix_confusable_glosses({"lexemes": [page2, sheet]})
    assert page2["relations"][0]["hide_by_default"] is True


def test_target_without_native_keeps_text():
    page = lex(1, "page", "noun", 0, ["頁"], [rel("pale", 2, "柵欄")])
    pale = lex(2, "pale", "adj", 0, [])
    fix_confusable_glosses({"lexemes": [page, pale]})
    assert page["relations"][0]["native"] == "柵欄"
