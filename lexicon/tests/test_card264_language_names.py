from app.text import repair_language_names, repair_learner_gloss


def test_german_french_names():
    assert repair_language_names('源自低地德國語 X，或德國語 Y。') == '源自低地德語 X，或德語 Y。'
    assert repair_language_names('受舊法國語與法國語影響') == '受古法語與法語影響'


def test_idempotent_and_empty():
    once = repair_language_names('德國語')
    assert repair_language_names(once) == once == '德語'
    assert repair_language_names(None) is None
    assert repair_language_names('') == ''


def test_learner_gloss_applies_it():
    assert repair_learner_gloss('From German X.', '源自德國語 X。') == '源自德語 X。'
