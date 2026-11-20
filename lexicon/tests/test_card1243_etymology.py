"""card #1243 (問題回報 #1691): an Etymology-tree node must not be taken as the sentence."""
from app.adapters import kaikki


def test_transliterated_tree_node_is_not_the_sentence():
    text = ("Etymology tree\nProto-Indo-Iranian *-ikas\nSanskrit -इक (-ika)\n"
            "Prakrit वेरुलिअ (vērulia)bor.\nItalian brillarebor.\nFrench briller\n"
            "Borrowed from Italian brillare.")
    assert kaikki._clean_etymology(text) == "Borrowed from Italian brillare."


def test_latin_node_with_parenthesis_is_skipped():
    text = "Etymology tree\nLatin contin(eō)\nFrench continuer\nInherited from Old French."
    assert kaikki._clean_etymology(text) == "Inherited from Old French."


def test_tree_label_with_influ_tag_is_skipped():
    text = "Etymology tree\nLatin mandōinflu.\nLatin commandāre\nPresent participle of commander."
    assert kaikki._clean_etymology(text) == "Present participle of commander."


def test_sentence_ending_in_word_der_is_kept():
    text = "Etymology tree\nFrench commander\nInherited from Middle French commander."
    assert kaikki._clean_etymology(text) == "Inherited from Middle French commander."
