import pytest

from app.text import repair_icelandic_gloss, repair_learner_gloss


@pytest.mark.parametrize('wrong', ['愛沙尼亞語', '愛斯蘭尼亞語', '愛爾蘭語'])
def test_icelandic_variants(wrong):
    en = 'Compare ICELANDIC X.'
    zh = f'與{wrong} X 同源。'
    expected = '與冰島語 X 同源。'
    assert repair_learner_gloss(en, zh) == expected
    assert repair_icelandic_gloss(en, expected) == expected
    assert repair_icelandic_gloss('Compare Estonian X.', zh) == zh
    assert repair_icelandic_gloss(None, zh) == zh
    assert repair_icelandic_gloss(en, None) is None


def test_real_language_names_preserved_independently():
    assert repair_icelandic_gloss('Irish X and Icelandic Y',
        '愛爾蘭語 X、愛沙尼亞語 Y') == '愛爾蘭語 X、冰島語 Y'
    assert repair_icelandic_gloss('Estonian X and Icelandic Y',
        '愛沙尼亞語 X、愛爾蘭語 Y') == '愛沙尼亞語 X、冰島語 Y'
    assert repair_icelandic_gloss('estonian X and Irish Y and Icelandic Z',
        '愛沙尼亞語 X、愛爾蘭語 Y、愛斯蘭尼亞語 Z') == '愛沙尼亞語 X、愛爾蘭語 Y、冰島語 Z'
