from app.adapters.ai import _paren_foreign_roots
from app.text import native_latin_issue


def test_bare_roots_are_parenthesised():
    out = _paren_foreign_roots("此名詞源於中古英語的 appel，意指蘋果")
    assert "（appel）" in out and native_latin_issue(out) is None


def test_existing_parens_untouched():
    assert _paren_foreign_roots("源自法語（fruit）") == "源自法語（fruit）"


def test_accented_roots_stay_whole():
    out = _paren_foreign_roots("源自拉丁語 pĕrvé 與 perméabilité")
    assert "（pĕrvé）" in out and "（perméabilité）" in out
    assert native_latin_issue(out) is None


def test_modifier_letters_stay_in_root():
    # card #1173 / 問題回報 #1639: "selbʰ-" was split as "（selb）ʰ-"
    assert _paren_foreign_roots("原始印歐語 *selbʰ- 變成") == "原始印歐語 *（selbʰ-） 變成"
