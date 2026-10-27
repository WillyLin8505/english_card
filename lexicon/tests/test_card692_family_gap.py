"""Card #692 (問題回報 #556): the word-family ceiling holds only within FAMILY_GAP levels."""
from app.adapters.local import FAMILY_GAP, family_limited

A1, A2, B1, C1, C2 = 0, 1, 2, 4, 5


def test_gap_is_two_levels():
    assert FAMILY_GAP == 2


def test_within_gap_the_ceiling_applies():
    # within the gap (B2 is 1 above an A2 ceiling, B1 is 2 above A1): the ceiling wins
    assert family_limited("B2", 1) == "A2"
    assert family_limited("B1", 0) == "A1"


def test_beyond_gap_the_frequency_estimate_decides():
    # dogged: dog A1 ceiling, frequency C1 (gap 4) -> C1, not A1
    assert family_limited("C1", 0) == "C1"
    assert family_limited("B2", 0) == "B2"  # gap 3 is beyond the gap


def test_no_ceiling_keeps_frequency():
    assert family_limited("C2", None) == "C2"
