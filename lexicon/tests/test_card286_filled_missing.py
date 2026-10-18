"""問題回報 #289 (card #286): items written outside resolve_field (card166_reselect's
example↔sense bindings) must not stay listed in ``missing``."""

from app import pipeline


def test_drop_filled_missing():
    items = [{"key": "e1", "slot": "e1", "example_key": "e1", "sense_key": "s1", "source": "local_calc"},
             {"key": "e2", "slot": "e2", "example_key": "e2", "sense_key": "s2", "source": "local_calc"}]
    # every listed slot now filled → complete
    assert pipeline.drop_filled_missing("example_sense", "partial", ["e1", "e2"], items) == ("complete", [])
    # a status of missing with items written by a tool → partial while a slot is left
    assert pipeline.drop_filled_missing("example_sense", "missing", ["e1", "e3"], items) == ("partial", ["e3"])
    # rows without items, settled rows and per-level fields are left alone
    assert pipeline.drop_filled_missing("example_sense", "missing", ["e1"], []) == ("missing", ["e1"])
    assert pipeline.drop_filled_missing("example_sense", "complete", [], items) == ("complete", [])
    assert pipeline.drop_filled_missing("example_sentences", "partial", ["A1"],
                                        [{"slot": "A1", "text": "x"}]) == ("partial", ["A1"])
