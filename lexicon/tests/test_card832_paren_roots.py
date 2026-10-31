from app.adapters.ai import _paren_foreign_roots
from app.text import native_latin_issue


def test_bare_roots_are_parenthesised():
    out = _paren_foreign_roots("此名詞源於中古英語的 appel，意指蘋果")
    assert "（appel）" in out and native_latin_issue(out) is None


def test_existing_parens_untouched():
    assert _paren_foreign_roots("源自法語（fruit）") == "源自法語（fruit）"
