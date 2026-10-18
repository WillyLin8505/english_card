from owned_fixture import fixture_owned_ids
from test_preview import word
from domain import live_exercise


def relation(id, label, meaning, kind='related', level='A1', pos='noun'):
    return dict(target_lexeme_id=id, target_word=label, translation=meaning,
                relation=kind, cefr=level, pos=pos, strength=.8, detail={})


def test_both_modes_prioritize_similar_spelling_over_same_level_general_relation():
    w = word(1, 'coat')
    w['senses'][0]['translation'] = '外套'
    w['examples'][0]['text'] = 'Put on your coat.'
    w['images'] = [dict(sense_id=1, sense_image_id=1)]
    w['relations'] = [relation(2, 'wardrobe', '衣櫥'),
                      relation(3, 'goat', '山羊', 'similar_spelling', 'A2'),
                      relation(4, 'boat', '小船', 'similar_spelling', 'A2')]
    for kind in ('similar', 'photo_choice'):
        result = live_exercise(w, kind, 1, owned_lexeme_ids=fixture_owned_ids(w))
        assert result['available']
        assert {o['label'] for o in result['options']} == {'coat', 'goat', 'boat'}


def test_meaning_overlap_with_answer_is_not_a_similar_distractor():
    w = word()
    w['senses'][0]['translation'] = '蘋果'
    w['relations'] = [relation(2, 'apple fruit', '蘋果', 'synonyms'),
                      relation(3, 'apply', '應用', 'similar_spelling'),
                      relation(4, 'pear', '梨子')]
    result = live_exercise(w, 'similar', 1, owned_lexeme_ids=fixture_owned_ids(w))
    assert result['available']
    assert {o['label'] for o in result['options']} == {'apple', 'apply', 'pear'}


def test_picture_visible_labels_still_excluded_despite_high_spelling_similarity():
    w = word(1, 'coat')
    w['senses'][0]['translation'] = '外套'
    w['images'] = [dict(sense_id=1, sense_image_id=1, tags=[{'word': 'goat'}])]
    w['relations'] = [relation(2, 'goat', '山羊', 'similar_spelling'),
                      relation(3, 'boat', '小船', 'similar_spelling'),
                      relation(4, 'jacket', '夾克')]
    result = live_exercise(w, 'photo_choice', 1, owned_lexeme_ids=fixture_owned_ids(w))
    assert result['available']
    assert {o['label'] for o in result['options']} == {'coat', 'boat', 'jacket'}
