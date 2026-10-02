import pytest
from conftest import DATA_RAW

wordnet_available = (DATA_RAW / "nltk_data" / "corpora" / "wordnet").exists()

pytestmark = pytest.mark.skipif(
    not wordnet_available,
    reason="data/raw/nltk_data/corpora/wordnet missing — run pipeline/download_data.py first",
)


@pytest.fixture(scope="module")
def adapter():
    from pipeline.sources.wordnet_adapter import WordNetAdapter

    return WordNetAdapter(str(DATA_RAW / "nltk_data"))


def test_lexical_example(adapter):
    result = adapter.get_lexical("example")
    assert result is not None
    assert any(d["pos"] == "noun" for d in result["definitions"])


def test_synonyms_example(adapter):
    result = adapter.get_synonyms("example")
    assert result is not None
    assert "instance" in [s.lower() for s in result]


def test_derivations_happy_to_happiness(adapter):
    # the exact worked example from spec-01-data-sources.html
    result = adapter.get_derivations("happy")
    assert result is not None
    assert any(d["word"] == "happiness" for d in result)


def test_unknown_word_returns_none(adapter):
    assert adapter.get_lexical("zzznotarealword") is None
    assert adapter.get_synonyms("zzznotarealword") is None
    assert adapter.get_derivations("zzznotarealword") is None
