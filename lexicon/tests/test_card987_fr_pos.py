import pytest
from app.adapters.local import _fr_guess_pos, LocalCalc
from app.adapters.base import Context

@pytest.mark.parametrize('sentence,forms,poses,expected', [
    ('Je lis ce livre.', {'ce'}, {'noun','det','pron'}, 'det'),
    ('Ce qui compte.', {'ce'}, {'noun','det','pron'}, 'pron'),
    ('Il est grand.', {'grand'}, {'noun','adj'}, 'adj'),
    ('Avec vous.', {'avec'}, {'adv','prep'}, 'prep'),
    ("Je veux que vous veniez.", {'que'}, {'conj','pron','adv'}, 'conj'),
    ('Si tu viens.', {'si'}, {'conj','pron','adv'}, 'conj'),
])
def test_context(sentence, forms, poses, expected):
    assert _fr_guess_pos(sentence, forms, poses) == expected

def test_explicit_dictionary_sense_is_preserved():
    ctx=Context('fr','en','ce',resolved={
        'definition':[{'pos':'noun','sense_key':'noun'}, {'pos':'det','sense_key':'det'}],
        'example_sentences':[{'text':'Ce livre.', 'key':'ex','sense_key':'noun'}]})
    result=LocalCalc().normalize('example_sense',None,ctx)
    assert result[0].value['sense_key']=='noun'
