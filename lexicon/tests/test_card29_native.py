from app.text import (accept_native_gloss, main_native_sense_key, native_latin_issue,
                       native_sense_keys, normalize_native_gloss, repair_icelandic_gloss,
                       repair_learner_gloss, repair_outlaw_gloss,
                       sense_skipped_for_native)
from app.adapters.base import Candidate, Context, localize, validate


def test_outlaw_is_not_stored_as_adultery():
    ety = ('From Old English ūtlaga (“outlaw”), borrowed from Old Norse útlagi '
           '(“outlaw, fugitive”). Cognate with Icelandic útlagi.')
    fixed = repair_outlaw_gloss(
        ety, "出於古英語 ūtlaga（「通姦者」），借自古諾斯語 útlagi（「通姦者、逃亡者」）。與愛爾蘭語 útlagi 同源。")
    assert "通姦" not in fixed
    assert "ūtlaga（「逃犯」）" in fixed
    assert "útlagi（「逃犯、被放逐者」）" in fixed
    assert "冰島語" in fixed
    assert repair_outlaw_gloss(
        "They found the outlaw's tracks near the river.",
        "他們在河邊發現了通姦者的蹤跡。") == "他們在河邊發現了逃犯的蹤跡。"
    assert repair_outlaw_gloss("adulterer", "通姦") == "通姦"
    assert repair_outlaw_gloss("fornicate", "通姦") == "通姦"
    again = repair_outlaw_gloss(
        "They found the outlaw's tracks near the river.", "他們在河邊發現了逃犯的蹤跡。")
    assert again == "他們在河邊發現了逃犯的蹤跡。"


def test_icelandic_is_not_stored_as_irish():
    en = 'Compare Norwegian lendeklede, Icelandic lendarklæði (“loincloth”).'
    zh = "與挪威語 lendeklede、愛爾蘭語 lendarklæði 同源。"
    fixed = repair_icelandic_gloss(en, zh)
    assert fixed == "與挪威語 lendeklede、冰島語 lendarklæði 同源。"
    assert repair_icelandic_gloss(en, fixed) == fixed
    assert repair_icelandic_gloss(
        "except possibly Irish sríab", "除愛爾蘭語 sríab 外") == "除愛爾蘭語 sríab 外"
    assert repair_icelandic_gloss(
        "Compare Old Irish X and Icelandic Y.", "愛爾蘭語 X") == "愛爾蘭語 X"
    assert repair_learner_gloss(en, zh) == fixed


def test_context_exceptions_do_not_hide_fragments():
    for value in ('DNA檢測', 'CD唱片', 'T 恤', 'CPU處理器', 'U 形桿', '2-64mm石粒', 'R&B音樂'):
        assert native_latin_issue(value) is None
    for value in ('背gammon遊戲', '船、CP', '冷 snap', 'cpu殘片', 'mm殘字', 'VT殘字'):
        assert native_latin_issue(value)


def test_gloss_normalization_preserves_information():
    assert normalize_native_gloss('極大的 discredit（失譽）') == '極大的 失譽（discredit）'
    for value in ('失譽（discredit）', 'X（稱為基本類別）',
                  'Pseudemys rubriventris（一種龜類）', 'Gulo gulo（狼獾）',
                  'DNA（基因）', 'resent（不及物動詞）', '背gammon遊戲'):
        assert normalize_native_gloss(value) == value


def test_producer_normalizes_before_validation():
    ctx = Context('en', 'zh-TW', 'disgrace')
    c = Candidate('native_definition', 'zh-TW', {'text': 'discredit（失譽）'}, 's')
    localize(c, ctx)
    assert c.value['text'] == '失譽（discredit）'
    assert validate(c, ctx) is None
    c.value['text'] = '背gammon遊戲'
    assert validate(c, ctx)


def test_historical_cached_candidate_is_rechecked():
    from types import SimpleNamespace
    from app.pipeline import stored_candidates
    class Result:
        def scalar_one_or_none(self):
            return SimpleNamespace(status='succeeded')
        def scalars(self):
            return self
        def all(self):
            return [SimpleNamespace(id=1, language='zh-TW', value={'text':'背gammon遊戲'},
                item_key='s', source='ai_translate', slot='s', source_record_id='',
                confidence=.6, license='', attribution='', raw_value=None,
                retrieved_at=None, valid=True, invalid_reason=None, snapshot_id=None)]
    class Session:
        def execute(self, query):
            return Result()
    candidates, _ = stored_candidates(Session(), Context('en','zh-TW','table'),
                                      'native_definition','ai_translate')
    assert not candidates[0].valid
    assert 'gammon' in candidates[0].invalid_reason


def test_short_gloss_rejects_a_translated_sentence_and_keeps_a_marked_name():
    assert accept_native_gloss('冷 snap') is None
    assert accept_native_gloss('') is None
    assert accept_native_gloss('棕櫚') == '棕櫚'
    assert accept_native_gloss('家貓（Felis catus）') == '家貓（Felis catus）'
    marked = accept_native_gloss('粉蝶（Pieridae）')
    assert marked == '粉蝶（Pieridae）'
    assert native_latin_issue(marked) is None
    # A translated definition sentence is not a gloss, even after the name is marked.
    assert accept_native_gloss('Cepora 屬的各種 Pieridae 蝶類，分布於熱帶') is None


def test_main_sense_is_required_and_obscure_senses_are_not():
    senses = [
        {'sense_key': 'tree', 'gloss': 'Any of various trees of the family Palmae.'},
        {'sense_key': 'old', 'labels': ['obsolete'], 'gloss': 'To flow.'},
        {'sense_key': 'form', 'gloss': 'simple past and past participle of bead'},
    ]
    assert main_native_sense_key(senses) == 'tree'
    assert native_sense_keys(senses) == {'tree'}
    assert sense_skipped_for_native(senses[1], 'tree')
    assert not sense_skipped_for_native(senses[0], 'tree')
