from app import qc


def _tags(levels):
    return [{"cefr": level} for level in levels]


def test_levels_under_5_lists_only_short_levels():
    tags = _tags(["A1"] * 5 + ["A2"] * 4 + ["B1"] * 5 + ["B2"] * 5 + ["C1"] * 5 + ["C2"] * 5)
    assert qc._levels_under(tags, 5) == ["A2"]


def test_levels_under_5_counts_missing_levels_as_short():
    assert qc._levels_under(_tags(["A1"] * 9), 5) == ["A2", "B1", "B2", "C1", "C2"]
    assert qc._levels_under(None, 5) == list(qc.CEFR_LEVELS)


def test_metric_counts_pictures_and_is_not_a_gate():
    pack = {"lexemes": [], "catalog_images": [
        {"id": 1, "tags": _tags(["A1"] * 5 + ["A2"] * 3)},
        {"id": 2, "tags": _tags(["A1"] * 5 + ["A2"] * 5 + ["B1"] * 5 + ["B2"] * 5 + ["C1"] * 5 + ["C2"] * 5)},
    ]}
    m = qc.metrics(pack, {})
    assert m["photos_level_under_5"] == 1
    assert not any(k == "photos_level_under_5" and k.startswith("v.") for k in m)
