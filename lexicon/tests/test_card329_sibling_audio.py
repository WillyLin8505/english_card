"""Card #329: a lexeme without a recording of its own borrows a sibling
part of speech's recording only when the two share an IPA."""

from app.materialize import ipa_by_pos, sibling_recordings


class _Asset:
    status = "ready"


def _assets(*pos_list):
    return [(_Asset(), {"pos": p, "url": f"https://x/{p}.ogg"}) for p in pos_list]


def test_homograph_with_same_ipa_borrows_the_recording():
    # être: Kaikki lists the sound only under the verb; the noun says /ɛtʁ/ too.
    ipa = ipa_by_pos([{"pos": "verb", "ipa": "/ɛtʁ/"}, {"pos": "verb", "ipa": "/ɛːtʁ/"},
                      {"pos": "noun", "ipa": "/ɛtʁ/"}, {"pos": "verb", "ipa": "[ɛt(ɾ)]"}])
    got = sibling_recordings("noun", _assets("verb"), ipa)
    assert [it["pos"] for _, it in got] == ["verb"]


def test_heteronym_keeps_its_own_voice():
    ipa = ipa_by_pos([{"pos": "noun", "ipa": "/ˈɹɛk.ɚd/"}, {"pos": "verb", "ipa": "/ɹɪˈkɔɹd/"}])
    assert sibling_recordings("verb", _assets("noun"), ipa) == []


def test_lexeme_without_ipa_does_not_borrow():
    ipa = ipa_by_pos([{"pos": "noun", "ipa": "/ˈɹɛk.ɚd/"}])
    assert sibling_recordings("verb", _assets("noun"), ipa) == []


def test_pos_less_ipa_counts_for_every_part_of_speech():
    ipa = ipa_by_pos([{"ipa": "/pa/"}])
    assert len(sibling_recordings("adv", _assets("noun"), ipa)) == 1


def test_own_pos_and_tts_are_not_siblings():
    ipa = ipa_by_pos([{"pos": "noun", "ipa": "/pa/"}, {"pos": "adv", "ipa": "/pa/"}])
    assets = _assets("adv") + [(None, {"tts": True})]
    got = sibling_recordings("adv", assets, ipa)
    assert got == []
