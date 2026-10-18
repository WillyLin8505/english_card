"""Version 1 card layout contract shared by publication and preview."""
import copy

SECTIONS = {'hint': '字首提示', 'meaning': '詞性與母語提示', 'answer': '答案單字',
            'pronunciation': '發音', 'senses': '逐義釋義', 'images': '詞義圖片',
            'examples': '例句與翻譯', 'forms': '詞形變化', 'relations': '詞彙關係',
            'etymology': '字根與詞源', 'sources': '來源資訊'}
RELATIONS = {'synonyms': '同義詞', 'antonyms': '反義詞', 'hypernyms': '上位詞', 'hyponyms': '下位詞',
             'related': '相關詞', 'homophones': '同音字', 'near_homophones': '近音字',
             'similar_spelling': '拼字相近', 'derived_terms': '衍生詞'}
LIMITS = {'hint': 3, 'meaning': 3, 'answer': 1, 'pronunciation': 10, 'senses': 20,
          'images': 3, 'examples': 10, 'forms': 30, 'relations': 20, 'etymology': 1, 'sources': 200}


def default_layout():
    sections = []
    for key in SECTIONS:
        sections.append({'key': key, 'side': 'front' if key in ('hint', 'meaning') else 'back',
                         'visible': True, 'limit': {'hint': 1, 'meaning': 1, 'answer': 1, 'pronunciation': 1,
                                                   'senses': 3, 'images': 1, 'examples': 5, 'forms': 5,
                                                   'relations': 3, 'etymology': 1, 'sources': 10}[key],
                         'collapsed': key in ('etymology', 'sources'), 'expand_all': True})
    return {'schema_version': 1, 'sections': sections, 'relation_limits': {k: 3 for k in RELATIONS},
            'show_ratings': True, 'show_translation': True, 'show_sources': True}


def validate_layout(layout):
    if not isinstance(layout, dict) or layout.get('schema_version') != 1:
        raise ValueError('不支援的模板格式；預覽格式需為 schema_version 1')
    items = layout.get('sections', [])
    if not isinstance(items, list):
        raise ValueError('模板區塊必須為清單')
    keys = [s.get('key') for s in items if isinstance(s, dict)]
    if len(keys) != len(items) or len(keys) != len(set(keys)) or set(keys) != set(SECTIONS):
        raise ValueError('模板區塊必須完整且不可重複')
    for s in items:
        key = s['key']
        if s.get('side') not in ('front', 'back'):
            raise ValueError('區塊位置必須為正面或背面')
        if s['side'] == 'front' and key not in ('hint', 'meaning'):
            raise ValueError('字卡正面只允許字首與母語提示，禁止答案、圖片或例句')
        if key == 'answer' and (s['side'] != 'back' or s.get('visible') is not True):
            raise ValueError('背面必須保留答案單字')
        if type(s.get('limit')) is not int or not 1 <= s['limit'] <= LIMITS[key]:
            raise ValueError(f'{SECTIONS[key]}數量需介於 1～{LIMITS[key]}')
        for flag in ('visible', 'collapsed', 'expand_all'):
            if type(s.get(flag)) is not bool:
                raise ValueError('區塊開關必須為布林值')
    if not any(s['side'] == 'front' and s['visible'] for s in items):
        raise ValueError('正面至少保留一個提示區塊')
    relation_limits = layout.get('relation_limits', {})
    if not isinstance(relation_limits, dict) or set(relation_limits) - set(RELATIONS):
        raise ValueError('關係詞設定格式錯誤')
    for flag in ('show_ratings', 'show_translation', 'show_sources'):
        if flag in layout and type(layout[flag]) is not bool:
            raise ValueError('顯示開關必須為布林值')
    for n in relation_limits.values():
        if type(n) is not int or not 0 <= n <= 20:
            raise ValueError('每類關係詞數量需介於 0～20')
    return copy.deepcopy(layout)

