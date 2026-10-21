"""Card #484 (問題回報 #479): an interjection / determiner card does not show the
adjective's comparative / superlative (good 感嘆詞 → better / best)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import app_pack  # noqa: E402

CMP = [{"field": "adj_comparative", "normalized": "better"},
       {"field": "adj_superlative", "normalized": "best"}]


def _forms(by_lex):
    app_pack.share_forms(by_lex)
    return {i: [f["field"] for f in lex["forms"]] for i, lex in by_lex.items()}


def test_interjection_beside_adjective_has_no_degree_forms():
    got = _forms({1: {"normalized": "good", "pos": "intj", "forms": []},
                  2: {"normalized": "good", "pos": "adj", "forms": [dict(f) for f in CMP]}})
    assert got == {1: [], 2: ["adj_comparative", "adj_superlative"]}


def test_determiner_without_adjective_sibling_keeps_forms():
    got = _forms({1: {"normalized": "many", "pos": "det", "forms": [dict(f) for f in CMP]}})
    assert got == {1: ["adj_comparative", "adj_superlative"]}
