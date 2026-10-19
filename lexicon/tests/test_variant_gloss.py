from app import quality


def test_variant_gloss_pattern():
    base = lambda g: (m.group(1).lower() if (m := quality.VARIANT_GLOSS_RE.match(g)) else None)
    assert base("US standard spelling of distil.") == "distil"
    assert base("Alternative form of cross section.") == "cross section"
    assert base("Non-Oxford British English standard spelling of demoralize.") == "demoralize"
    assert base("Alternative form of whiskey (“a light gig or carriage”).") == "whiskey"
    assert base("A form of roleplaying which is inconsequential.") is None
    assert base("The liquid form of this substance.") is None


def test_alt_of_sense_is_a_base():
    sense = {"glosses": ["Alternative spelling of badmouth"], "alt_of": [{"word": "badmouth"}]}
    assert quality._sense_base(sense, "bad-mouth") == "badmouth"
