from pipeline.sources.wordlist_adapter import LocalWordlistAdapter, _levenshtein


def test_levenshtein_basic():
    assert _levenshtein("cat", "cat") == 0
    assert _levenshtein("cat", "bat") == 1
    assert _levenshtein("cat", "cats") == 1
    assert _levenshtein("", "abc") == 3


def test_similar_spelling_finds_edit_distance_one():
    words = ["cat", "bat", "hat", "mat", "dog", "cats"]
    adapter = LocalWordlistAdapter(words)
    result = adapter.get_similar_spelling("cat", max_distance=1)
    assert result is not None
    assert set(result) == {"bat", "hat", "mat", "cats"}
    assert "dog" not in result


def test_similar_spelling_excludes_exact_word():
    adapter = LocalWordlistAdapter(["cat", "bat"])
    result = adapter.get_similar_spelling("cat", max_distance=1)
    assert "cat" not in result


def test_similar_spelling_none_when_no_neighbors():
    adapter = LocalWordlistAdapter(["zzz", "yyy"])
    assert adapter.get_similar_spelling("cat", max_distance=1) is None


def test_similar_spelling_respects_limit():
    words = [f"ca{c}" for c in "bdfghjklmnpqrstvwxyz"]  # 20 neighbors of "cat"-ish
    adapter = LocalWordlistAdapter(words + ["cat"])
    result = adapter.get_similar_spelling("cat", max_distance=1, limit=3)
    assert len(result) == 3
