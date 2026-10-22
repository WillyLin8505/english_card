from app.text import fr_unfit_text, unsafe_gloss


def test_french_profane_sentence():
    assert fr_unfit_text("Un pénis sectionné constitue une pièce à conviction.", "constituer")
    assert fr_unfit_text("Dieu merci, Apple met cette merde de Flash au rebut !", "dieu")
    assert not fr_unfit_text("Nous nous sommes amusés au pique-nique.", "pique-nique")
    assert not fr_unfit_text("Le jury a estimé que Samsung a violé les brevets.", "jury")
    assert not fr_unfit_text("C'est de la merde.", "merde")  # headword's own word


def test_unsafe_gloss():
    assert unsafe_gloss("wet, moist (of a woman, sexually excited)")
    assert unsafe_gloss("member, penis")
    assert not unsafe_gloss("protection (means, such as a condom, of preventing pregnancy)")
    assert not unsafe_gloss("cat (feline)")
