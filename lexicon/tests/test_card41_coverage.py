"""Inventory must not disappear merely because a pair has no extraction rows."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import pytest

from app.views import coverage


@pytest.fixture
def inventory():
    engine = create_engine("sqlite://")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE lexemes (normalized TEXT, language TEXT, status TEXT)"))
        c.execute(text("CREATE TABLE field_values (lemma TEXT, target_language TEXT, "
                       "native_language TEXT, field TEXT, status TEXT)"))
        c.execute(text("INSERT INTO lexemes VALUES "
                       "('apple','en','full'),('apple','en','stub'),"
                       "('banana','en','stub'),('cherry','en','full'),"
                       "('pomme','fr','full')"))
        c.execute(text("INSERT INTO field_values VALUES "
                       "('apple','en','zh-TW','definition','complete'),"
                       "('apple','en','zh-TW','native_definition','failed'),"
                       "('cherry','en','ja','definition','complete'),"
                       "('detached','en','zh-TW','definition','missing')"))
    with Session(engine) as s:
        yield s
    engine.dispose()


def test_union_preserves_catalog_and_field_only_words(inventory):
    result = coverage(inventory, "en", "zh-TW")
    assert [w["lemma"] for w in result["words"]] == ["apple", "banana", "cherry", "detached"]
    assert result["total_words"] == 4
    assert result["full_words"] == 2
    assert result["stub_words"] == 1 and result["fields_only_words"] == 1
    assert result["resolved_words"] == 2
    apple, banana, cherry, _ = result["words"]
    assert apple["status"] == "full"  # a secondary stub POS cannot downgrade it
    assert apple["target"] == [1, 1] and apple["native"] == [0, 1]
    assert apple["failed"] == 1
    assert banana["target"] == [0, 0] and not banana["has_fields"]
    assert not cherry["has_fields"]  # Japanese extraction is not Chinese coverage


def test_pagination_is_complete_and_non_overlapping(inventory):
    pages = [coverage(inventory, "en", "zh-TW", limit=2, offset=i) for i in (0, 2, 4)]
    assert [w["lemma"] for p in pages for w in p["words"]] == ["apple", "banana", "cherry", "detached"]
    assert all(p["matched"] == 4 for p in pages)


@pytest.mark.parametrize("only,expected", [
    ("full", ["apple", "cherry"]), ("stub", ["banana"]),
    ("not_run", ["banana", "cherry"]), ("failed", ["apple"]),
    ("incomplete", ["apple", "banana", "cherry", "detached"]),
])
def test_filters(inventory, only, expected):
    result = coverage(inventory, "en", "zh-TW", only=only)
    assert [w["lemma"] for w in result["words"]] == expected
    assert result["total_words"] == 4


def test_search_finds_unextracted_words(inventory):
    result = coverage(inventory, "en", "zh-TW", q="BAN")
    assert result["matched"] == 1 and result["words"][0]["lemma"] == "banana"


def test_new_pair_keeps_inventory_without_claiming_coverage(inventory):
    result = coverage(inventory, "en", "ko")
    assert result["total_words"] == 3 and result["resolved_words"] == 0
    assert result["fields"] == []
    assert all(not w["has_fields"] for w in result["words"])


def test_field_qc_counts_are_not_diluted_by_stubs(inventory):
    fields = {f["field"]: f for f in coverage(inventory, "en", "zh-TW")["fields"]}
    assert fields["definition"]["counts"] == {"complete": 1, "missing": 1}
    assert fields["definition"]["rate"] == 0.5
    assert fields["native_definition"]["counts"] == {"failed": 1}
    assert fields["native_definition"]["rate"] == 0
