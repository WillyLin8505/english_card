from app.quality import example_other_pos_only


def test_other_pos_inflection_is_rejected():
    assert example_other_pos_only("Fast charging is useful.", "charge", ["charges"], ["charged", "charging"])
    assert example_other_pos_only("It is the deepest lake.", "deep", ["deeper"], ["deepest"])
    assert example_other_pos_only("Sweets are bad for teeth.", "sweet", ["sweeter"], ["sweets"])


def test_own_word_or_own_form_is_kept():
    assert not example_other_pos_only("Charge the phone.", "charge", [], ["charging"])
    assert not example_other_pos_only("She is easier to talk to.", "easy", ["easier"], ["easies"])
    assert not example_other_pos_only("Fancies are rare.", "fancy", [], [])  # no sibling owns it
