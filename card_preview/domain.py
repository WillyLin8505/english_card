"""Pure preview rules; deliberately has no learning-state writer."""
import copy
import re
import math
import random
from difflib import SequenceMatcher


def entry_type_of(normalized):
    """spec-01 §7 片語標籤: a multi-token normalized form is a phrase.

    Mirrors lexicon/backend/app/text.entry_type_of exactly. Duplicated (not
    imported) because this module is a read-only boundary that never imports
    the mutable lexicon app; the rule is a stable one-liner, so keeping both
    copies in sync by hand is low-risk.
    """
    return 'phrase' if ' ' in (normalized or '').strip() else 'word'


def confusable_rank(word, relation):
    """Prefer actual spelling similarity or documented semantic proximity.

    Level and part of speech break ties; they must not make an unrelated
    same-level word outrank a genuinely confusable one.
    """
    label = relation.get('target_word', '').strip().casefold()
    spelling = SequenceMatcher(None, word['lemma'].casefold(), label).ratio()
    kind = relation.get('relation')
    semantic = {'synonyms': .92, 'hyponyms': .86, 'hypernyms': .86,
                'related': .70, 'antonyms': .65, 'derived_terms': .55}.get(kind, 0)
    strength = max(0, min(1, float(relation.get('strength') or 0)))
    proximity = max(semantic + .1 * strength if semantic else 0,
                    .8 + .2 * spelling if spelling >= .65 else 0)
    levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
    level, other = word.get('cefr'), relation.get('cefr')
    gap = abs(levels.index(level) - levels.index(other)) if level in levels and other in levels else 3
    return (-proximity, relation.get('pos') != word.get('pos'), gap, -strength, label)

# A drag question places exactly this many labels (owner 2026-10-14:
# 拖曳題目固定為要拖曳 3 個項目).
DRAG_OPTIONS = 3

KINDS = [
    {'id': 'cloze', 'name': '句子填空', 'icon': '＿', 'description': '閱讀實際例句，輸入缺少的單字', 'needs': '配對例句'},
    {'id': 'photo_choice', 'name': '看圖選單字', 'icon': '▧', 'description': '看圖片，點選對應的單字', 'needs': '已核准詞義圖片、不重疊選項'},
    {'id': 'similar', 'name': '相似詞比較', 'icon': '≈', 'description': '閱讀情境句，從相近詞中選出最自然的答案', 'needs': '有翻譯的例句與至少兩個相近詞'},
    {'id': 'photo_recall', 'name': '母語說明＋照片', 'icon': '◉', 'description': '結合圖片情境，主動回想單字', 'needs': '母語釋義、同義項已核准圖片'},
    {'id': 'drag', 'name': '拖曳單字到圖片', 'icon': '↗', 'description': '把詞籤放到正確的圖片位置', 'needs': '已核准圖片、已驗證標籤框與詞義對應'},
]
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
    for n in layout.get('relation_limits', {}).values():
        if type(n) is not int or not 0 <= n <= 20:
            raise ValueError('每類關係詞數量需介於 0～20')
    return copy.deepcopy(layout)


def text_valid(value):
    return isinstance(value, str) and bool(value.strip()) and '\ufffd' not in value


GLOSS_SPLIT = re.compile(r'[\u3001\uff0c,;\uff1b/\uff0f|\uff5c]+')


def gloss_keys(text):
    """Split a native gloss such as '\u6177\u6168\u3001\u5927\u65b9' into comparable meanings."""
    keys = set()
    for part in GLOSS_SPLIT.split(text or ''):
        part = re.sub(r'[\uff08(][^\uff09)]*[\uff09)]', '', part)
        part = re.sub(r'\s+', ' ', part).strip().casefold()
        if part:
            keys.add(part)
    return keys


def glosses_overlap(a, b):
    """True when two glosses share a meaning, which would make a matching pair ambiguous."""
    for x in gloss_keys(a):
        for y in gloss_keys(b):
            short, long = sorted((x, y), key=len)
            if short == long or (len(short) >= 2 and short in long):
                return True
    return False


def match_payload(pairs, seed):
    """Two independently shuffled columns; every pair never sits on the same row."""
    rng = random.Random(seed)
    targets = [p['id'] for p in pairs]
    natives = targets[:]
    rng.shuffle(targets)
    rng.shuffle(natives)
    if natives == targets:
        natives = natives[1:] + natives[:1]
    return {'available': True, 'mode': 'match', 'pairs': pairs,
            'native_order': natives, 'target_order': targets, 'correct_id': pairs[0]['id'],
            'prompt': '\u628a\u610f\u601d\u76f8\u540c\u7684\u5169\u500b\u8a5e\u9023\u8d77\u4f86',
            'instruction': '\u5148\u9ede\u4e00\u908a\u7684\u8a5e\uff0c\u518d\u9ede\u53e6\u4e00\u908a\u5c0d\u61c9\u7684\u8a5e\uff1b\u4e09\u7d44\u90fd\u9023\u5c0d\u5c31\u5b8c\u6210\u3002'}


def quality(word):
    missing = []
    if not word.get('pos') or word['pos'] in ('unknown', ''):
        missing.append({'field': 'pos', 'message': '缺少詞性'})
    if not word['senses']:
        missing.append({'field': 'senses', 'message': '尚未匯入義項'})
    for s in word['senses']:
        if not text_valid(s.get('translation')):
            missing.append({'field': 'sense:' + str(s['id']), 'message': f'義項 #{s["id"]} 缺少有效母語釋義'})
    for e in word['examples']:
        if not text_valid(e.get('translation')):
            missing.append({'field': 'example:' + str(e['id']), 'message': f'例句 #{e["id"]} 缺少有效母語翻譯'})
    for e in word.get('rejected_examples', []):
        missing.append({'field': 'example:' + str(e['id']),
                        'message': (f'例句 #{e["id"]} 是詞彙欄位清單，已從學習卡排除'
                                    if is_column_word_list(e.get('text'), word.get('lemma')) else
                                    f'例句 #{e["id"]} 未包含此詞性的單字或正式詞形，已從學習卡排除')})
    if len(word['examples']) < 5:
        missing.append({'field': 'examples', 'message': f'例句只有 {len(word["examples"])} 組，規格目標至少 5 組'})
    for r in word['relations']:
        if not text_valid(r.get('translation')):
            missing.append({'field': 'relation:' + str(r['id']), 'message': f'{r["target_word"]} 缺少母語詞義'})
    return missing


MERGE_KEYS = {
    'senses': None, 'examples': None, 'images': None,
    'forms': lambda x: (str(x.get('form', '')).casefold(), x.get('field')),
    'relations': lambda x: (x.get('relation'), str(x.get('target_word', '')).casefold()),
    'pronunciations': lambda x: (x.get('kind'), x.get('value'), x.get('accent')),
    'audio': lambda x: x.get('id'),
    'etymology': lambda x: (x.get('text'), x.get('translation')),
}


IRREGULAR_FORMS = {
    'be': {'am', 'is', 'are', 'was', 'were', 'been', 'being'},
    'child': {'children'}, 'person': {'people'}, 'man': {'men'}, 'woman': {'women'},
    'mouse': {'mice'}, 'goose': {'geese'}, 'tooth': {'teeth'}, 'foot': {'feet'},
    'go': {'went', 'gone'}, 'do': {'did', 'done'}, 'have': {'had'}, 'make': {'made'},
    'take': {'took', 'taken'}, 'come': {'came'}, 'see': {'saw', 'seen'},
    'get': {'got', 'gotten'}, 'say': {'said'}, 'know': {'knew', 'known'},
    'think': {'thought'}, 'buy': {'bought'}, 'bring': {'brought'},
    'teach': {'taught'}, 'catch': {'caught'}, 'run': {'ran'}, 'eat': {'ate', 'eaten'},
    'drink': {'drank', 'drunk'}, 'write': {'wrote', 'written'},
    'speak': {'spoke', 'spoken'}, 'drive': {'drove', 'driven'},
    'give': {'gave', 'given'}, 'choose': {'chose', 'chosen'},
    'fall': {'fell', 'fallen'}, 'feel': {'felt'}, 'leave': {'left'},
    'keep': {'kept'}, 'sleep': {'slept'}, 'meet': {'met'},
    'good': {'better', 'best'}, 'bad': {'worse', 'worst'},
}


def plausible_form(lemma, form):
    """Conservative guard against source forms that are another word.

    Stored forms remain visible for inspection, but only forms with a normal
    inflectional relationship (or a small common-irregular list) can admit an
    example into a learning card.
    """
    lemma, form = str(lemma or '').casefold(), str(form or '').casefold()
    if lemma == form or form in IRREGULAR_FORMS.get(lemma, set()):
        return True
    if ' ' in lemma:
        before, head = lemma.rsplit(' ', 1)
        return form.startswith(before + ' ') and plausible_form(head, form[len(before) + 1:])
    if form.startswith(lemma) and form[len(lemma):] in {'s', 'es', 'd', 'ed', 'ing', 'er', 'est'}:
        return True
    stems = {lemma}
    if lemma and lemma[-1].isalpha() and lemma[-1] not in 'aeiouy':
        stems.add(lemma + lemma[-1])
    if lemma.endswith('e'):
        stems.add(lemma[:-1])
    if lemma.endswith('y'):
        stems.add(lemma[:-1] + 'i')
    if lemma.endswith('f'):
        stems.add(lemma[:-1] + 'v')
    if lemma.endswith('fe'):
        stems.add(lemma[:-2] + 'v')
    return any(form.startswith(stem) and form[len(stem):] in {'s', 'es', 'd', 'ed', 'ing', 'er', 'est'}
               for stem in stems)


def example_uses_headword(word, example, usage_forms=None):
    """Whether an example contains this exact usage's lemma or stored form.

    A shared spelling can have multiple POS lexemes.  Forms from another POS
    must not make an unrelated example valid (noun ``mug`` versus verb
    ``mugged``), and prefixes such as ``happy`` in ``happiness`` are not uses
    of the card word.
    """
    usage = example.get('lexeme_id')
    forms = {str(word.get('lemma') or '').strip()}
    candidates = ((usage_forms or {}).get(usage) if usage_forms is not None else
                  [item for item in word.get('forms', []) if item.get('lexeme_id') == usage]) or []
    forms.update(str(item.get('form') or '').strip() for item in candidates
                 if plausible_form(word.get('lemma'), item.get('form')))
    forms.discard('')
    text = str(example.get('text') or '')
    if is_column_word_list(text, word.get('lemma')):
        return False
    if str(word.get('language') or '').startswith('zh'):
        return any(form in text for form in forms)
    return any(re.search(r"(?<![\w'’])" + re.escape(form) + r"(?![\w'’])", text, re.I)
               for form in forms)


def is_column_word_list(text, lemma):
    parts = [p.strip() for p in re.split(r"\t+|[\u2002-\u200a]{2,}| {3,}", text or '') if p.strip()]
    head = (lemma or '').strip().lower()
    return bool(head) and len(parts) >= 2 and all(
        p == p.lower() and re.fullmatch(r"[a-z'’ -]+", p)
        and len(p.split()) <= 4 and (p == head or p.endswith(' ' + head))
        for p in parts)


def merge_usages(cards):
    """One card per spelling (spec 07): the lexicon stores each POS as its own lexeme.

    ``cards`` are the lexemes of one spelling, most common usage first. Every item
    keeps the ``lexeme_id``/``usage_pos`` it came from, so exercises still run on
    the usage that owns the chosen sense.
    """
    word = copy.deepcopy(cards[0])
    word['usages'] = [{'lexeme_id': c['id'], 'pos': c.get('pos'), 'cefr': c.get('cefr'),
                       'zipf': c.get('zipf'), 'status': c.get('status'), 'updated_at': c.get('updated_at')}
                      for c in cards]
    for key, identity in MERGE_KEYS.items():
        items, seen = [], set()
        for card in cards:
            for item in card.get(key, []):
                mark = identity(item) if identity else None
                if mark is not None and mark in seen:
                    continue
                seen.add(mark)
                items.append({**copy.deepcopy(item), 'lexeme_id': card['id'], 'usage_pos': card.get('pos')})
        word[key] = items
    examples = word['examples']
    usage_forms = {card['id']: card.get('forms', []) for card in cards}
    word['examples'] = [item for item in examples if example_uses_headword(word, item, usage_forms)]
    word['rejected_examples'] = [item for item in examples if not example_uses_headword(word, item, usage_forms)]
    return word


def owned_candidates(candidates, owned_lexeme_ids, id_key='id'):
    """A dictionary lookup is not ownership. Missing scope fails closed.

    Callers supply the active personal library, excluding archived entries.
    Both live relations and reviewed packets use this same membership gate.
    """
    owned = frozenset(owned_lexeme_ids or ())
    return [candidate for candidate in candidates if candidate.get(id_key) in owned]


def prepare_exercise(word, kind, sense_id, bundle=None, option_cards=None, *, owned_lexeme_ids=None):
    """Require real references and an explicit upstream validation for distractors.

    A JSON packet contains IDs and review explanations only, never copied word data.
    No random words are promoted to validated distractors.
    """
    sense = next((s for s in word['senses'] if s['id'] == sense_id), None)
    reasons = []
    restricted = kind in ('similar', 'photo_choice', 'cloze', 'drag')
    if restricted and not owned_candidates([word], owned_lexeme_ids):
        reasons.append('缺少使用者持有詞庫，或本題單字不在持有詞庫中')
    if not sense or not text_valid(sense.get('translation')):
        reasons.append('目前義項缺少有效母語釋義')
    if not word.get('pos') or word['pos'] == 'unknown':
        reasons.append('缺少詞性')
    images = [i for i in word['images'] if i['sense_id'] == sense_id]
    payload = {'kind': kind, 'sense_id': sense_id, 'available': False, 'reasons': reasons}
    if kind in ('photo_choice', 'photo_recall', 'drag') and not images:
        reasons.append('目前義項沒有已核准且可用的圖片')
    if kind == 'photo_recall':
        payload.update(available=not reasons, images=images)
        return payload
    if not bundle:
        reasons.append('尚無已驗證的題目資料；不自動拼湊選項或圖片標籤框')
        return payload
    if bundle.get('kind') != kind or bundle.get('lexeme_id') != word['id'] or bundle.get('sense_id') != sense_id or bundle.get('native_language') != word['native_language'] or bundle.get('target_language') != word['language']:
        reasons.append('題目與目前語言／詞條／義項不一致')
    check = bundle.get('validation', {})
    if check.get('status') != 'approved' or not check.get('reviewer') or not check.get('reason') or not check.get('checked_at'):
        reasons.append('缺少題目審核者、時間或答案唯一性理由')
    if bundle.get('lexeme_updated_at') != str(word['updated_at']):
        reasons.append('詞條資料已更新，題目需要重新驗證')
    payload['validation'] = check
    if kind == 'cloze':
        example = next((e for e in word['examples'] if e['id'] == bundle.get('example_id') and e.get('sense_id') == sense_id), None)
        answer = bundle.get('answer_form', '')
        forms = [word['lemma']] + [f['form'] for f in word['forms']]
        if not example or not text_valid(example.get('translation')):
            reasons.append('缺少對應義項且有母語翻譯的例句')
        elif not isinstance(answer, str) or answer.casefold() not in [f.casefold() for f in forms]:
            reasons.append('正確答案不是此詞條的合法詞形')
        else:
            pattern = re.compile(r'(?<!\w)' + re.escape(answer) + r'(?!\w)', re.I)
            if len(pattern.findall(example['text'])) != 1:
                reasons.append('例句中的答案位置不唯一或不存在')
            else:
                masked = pattern.sub('＿＿＿＿', example['text'])
                if answer.casefold() in masked.casefold():
                    reasons.append('例句遮罩後仍出現答案字串')
                else:
                    payload.update(prompt=masked, example=example)
    if kind in ('photo_choice', 'drag'):
        image = next((i for i in images if i['sense_image_id'] == bundle.get('sense_image_id')), None)
        if not image:
            reasons.append('題目圖片不是目前義項的已核准圖片')
        payload['image'] = image
    options = bundle.get('options', [])
    if not isinstance(options, list):
        options = []
    low, high = (DRAG_OPTIONS, DRAG_OPTIONS) if kind == 'drag' else ((3, 3) if kind == 'similar' else (3, 5))
    if not low <= len(options) <= high:
        reasons.append(f'選項數量需為 {low} 個' if low == high else f'選項數量需介於 {low}～{high}')
    output = []
    for o in options:
        card = (option_cards or {}).get(o.get('lexeme_id'))
        if restricted and not owned_candidates([card] if card else [], owned_lexeme_ids):
            reasons.append('選項不在使用者持有詞庫中；不提供此題型')
            continue
        osense = next((s for s in card['senses'] if s['id'] == o.get('sense_id')), None) if card else None
        if not card or card['language'] != word['language'] or not osense or not text_valid(osense.get('translation')):
            reasons.append('選項缺少真實詞條、義項或母語翻譯')
            continue
        label = o.get('form', card['lemma'])
        if label.casefold() not in [x.casefold() for x in [card['lemma']] + [f['form'] for f in card['forms']]]:
            reasons.append('選項詞形無法在資料庫中驗證')
        if kind != 'drag' and card['pos'] != word['pos']:
            reasons.append('干擾選項詞性不相容')
        levels = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
        if kind != 'drag' and (card.get('cefr') not in levels or word.get('cefr') not in levels or abs(levels.index(card['cefr'])-levels.index(word['cefr'])) > 1):
            reasons.append('選項難度未知或相差超過一級')
        if not o.get('reason'):
            reasons.append('缺少逐項用法／適用情境說明')
        if str(card['updated_at']) != o.get('lexeme_updated_at'):
            reasons.append('選項詞條已更新，需要重新驗證')
        if kind == 'similar' and card['id'] != word['id'] and card['id'] not in [r['target_lexeme_id'] for r in word['relations']]:
            reasons.append('相似詞選項沒有詞彙關係依據')
        box = o.get('box')
        if kind == 'drag' and (not isinstance(box, list) or len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                               or min(box) < 0 or box[2] <= 0 or box[3] <= 0 or box[0]+box[2] > 1 or box[1]+box[3] > 1):
            reasons.append('拖曳區域座標無效')
        output.append({'id': card['id'], 'sense_id': osense['id'], 'label': label, 'translation': osense['translation'],
                       'pos': card['pos'], 'reason': o.get('reason'), 'box': box})
    if len({o['id'] for o in output}) != len(output) or len({o['label'].casefold() for o in output}) != len(output):
        reasons.append('選項重複')
    correct = [o for o in output if o['id'] == word['id'] and o['sense_id'] == sense_id]
    if kind != 'drag' and len(correct) != 1:
        reasons.append('必須恰有一個正確義項選項')
    if kind == 'cloze' and correct and correct[0]['label'].casefold() != bundle.get('answer_form', '').casefold():
        reasons.append('正確選項與例句詞形不一致')
    if kind == 'similar' and any(glosses_overlap(a['translation'], b['translation'])
                                 for i, a in enumerate(output) for b in output[i + 1:]):
        reasons.append('選項的母語詞義重疊，連線答案不唯一')
    payload.update(id=bundle.get('id'), options=output, correct_id=word['id'], available=not reasons,
                   reasons=list(dict.fromkeys(reasons)))
    if kind == 'similar' and payload['available']:
        names = {r.get('target_lexeme_id'): RELATIONS.get(r.get('relation'), '相似詞') for r in word['relations']}
        pairs = sorted(({**o, 'relation': '本題單字' if o['id'] == word['id'] else names.get(o['id'], '相似詞')}
                        for o in output), key=lambda o: o['id'] != word['id'])
        payload.update(match_payload(pairs, f"{bundle.get('id')}:similar-match-v1"))
    return payload


def live_exercise(word, kind, sense_id, *, owned_lexeme_ids=None):
    """Read-only practice from real records; never asserts reviewed distractors."""
    base = {'kind': kind, 'sense_id': sense_id, 'available': False, 'reasons': []}
    if kind in ('similar', 'photo_choice') and not owned_candidates([word], owned_lexeme_ids):
        base['reasons'] = ['缺少使用者持有詞庫，或本題單字不在持有詞庫中']
        return base
    relations = owned_candidates(word['relations'], owned_lexeme_ids, 'target_lexeme_id')
    if kind == 'photo_choice':
        images = [i for i in word['images'] if i['sense_id'] == sense_id]
        sense = next((s for s in word['senses'] if s['id'] == sense_id), None)
        if not images:
            base['reasons'] = ['這個義項尚無已核准圖片；請切換詞義或詞條。']
            return base
        if not sense or not text_valid(sense.get('translation')):
            base['reasons'] = ['這個義項尚無有效母語釋義。']
            return base

        candidates = []
        seen = {word['lemma'].casefold()}
        seen_ids = {word['id']}
        # A synonym or taxonomic label can also describe the pictured object.
        # Exclude its spelling across every relation group, including duplicates
        # imported as generic related words by another source.
        ambiguous_labels = {r.get('target_word', '').strip().casefold()
                            for r in word['relations']
                            if r.get('relation') in ('synonyms', 'hypernyms', 'hyponyms')}
        for relation in relations:
            label = relation.get('target_word', '').strip()
            if (not label or relation.get('target_lexeme_id') in seen_ids
                    or label.casefold() in seen or label.casefold() in ambiguous_labels
                    or not text_valid(relation.get('translation'))
                    or glosses_overlap(sense['translation'], relation.get('translation'))):
                continue
            detail = relation.get('detail') or {}
            if (relation.get('hide_by_default') is True or detail.get('hide_by_default') is True):
                continue
            candidates.append((*confusable_rank(word, relation), relation))
            seen.add(label.casefold())
            seen_ids.add(relation['target_lexeme_id'])
        candidates.sort(key=lambda item: item[:-1])
        # A visible image label cannot be called "not matching this picture".
        # Try other pictures of this sense before declaring data insufficient.
        image = None
        for candidate_image in images:
            visible = {str(tag.get(key) or '').strip().casefold()
                       for tag in candidate_image.get('tags', [])
                       if isinstance(tag, dict) for key in ('word', 'cefrLemma')}
            eligible = [item for item in candidates
                        if item[-1]['target_word'].strip().casefold() not in visible]
            if len(eligible) >= 2:
                image, candidates = candidate_image, eligible
                break
        if image is None:
            base['reasons'] = ['使用者持有的字中，排除同義詞、上下位詞、意思重疊及圖片已標示的可見詞後，需要至少兩個有母語釋義的比較詞，才能組成三選一題目。']
            return base

        options = [{'id': word['id'], 'sense_id': sense_id, 'label': word['lemma'],
                    'translation': sense['translation'], 'pos': word['pos'],
                    'reason': '這是圖片對應的正確標籤。'}]
        options.extend({'id': r['target_lexeme_id'], 'sense_id': None,
                        'label': r['target_word'], 'translation': r['translation'],
                        'pos': r.get('pos'),
                        'reason': f"{RELATIONS.get(r.get('relation'), r.get('relation', '相關詞'))}，但不符合這張圖片。"}
                       for r in [item[-1] for item in candidates[:2]])
        random.Random(f"{word['id']}:{sense_id}:photo-choice-v1").shuffle(options)
        return {**base, 'available': True, 'mode': 'photo_choice',
                'image': image, 'options': options, 'correct_id': word['id'],
                'prompt': '哪個單字最適合當作這張圖片的標籤？',
                'instruction': '觀察圖片，從三個相近的單字中選出最適合的標籤。'}
    if kind == 'cloze':
        forms = sorted({word['lemma'], *[f['form'] for f in word['forms']]}, key=len, reverse=True)
        blocked = set()
        for example in word['examples']:
            if example.get('sense_id') != sense_id or not text_valid(example.get('translation')):
                continue
            for form in forms:
                pattern = re.compile(r'(?<!\w)' + re.escape(form) + r'(?!\w)', re.I)
                matches = list(pattern.finditer(example['text']))
                if len(matches) == 1:
                    masked = pattern.sub('＿＿＿＿', example['text'])
                    if any(candidate.casefold() in masked.casefold() for candidate in forms if candidate):
                        blocked.add('例句遮罩後仍出現答案詞形或字母片段；為避免提示答案，暫不提供這一題。')
                        continue
                    return {**base, 'available': True, 'mode': 'typed', 'prompt': masked,
                            'answer': matches[0].group(), 'example': example,
                            'instruction': '請填入目前詞條在原始例句中的詞形。'}
                elif len(matches) > 1:
                    blocked.add('例句中出現多個答案位置，無法建立單一填空；請切換詞義或詞條。')
        base['reasons'] = sorted(blocked) or ['這個義項尚無包含本詞、且有翻譯的例句；請切換詞義或詞條。']
    elif kind == 'similar':
        sense = next((s for s in word['senses'] if s['id'] == sense_id), None)
        if not sense or not text_valid(sense.get('translation')):
            base['reasons'] = ['這個義項尚無有效母語釋義。']
            return base
        context = live_exercise(word, 'cloze', sense_id)
        if not context.get('available'):
            base['reasons'] = ['這個義項需要一個包含本詞、且有母語翻譯的情境句。']
            return base
        semantic = {'synonyms', 'hypernyms', 'hyponyms', 'related', 'similar_spelling'}
        candidates, seen = [], {word['lemma'].casefold()}
        for relation in relations:
            label = relation.get('target_word', '').strip()
            detail = relation.get('detail') or {}
            if (relation.get('relation') not in semantic or not label
                    or label.casefold() in seen or not text_valid(relation.get('translation'))
                    or glosses_overlap(sense['translation'], relation.get('translation'))
                    or (relation.get('hide_by_default') is True or detail.get('hide_by_default') is True)):
                continue
            candidates.append((*confusable_rank(word, relation), relation))
            seen.add(label.casefold())
        candidates.sort(key=lambda item: item[:-1])

        chosen = []
        for relation in [item[-1] for item in candidates]:
            if (relation['target_lexeme_id'] in [word['id']] + [r['target_lexeme_id'] for r in chosen]
                    or any(glosses_overlap(relation['translation'], r['translation']) for r in chosen)):
                continue
            chosen.append(relation)
            if len(chosen) == 2:
                break
        if len(chosen) < 2:
            base['reasons'] = ['使用者持有的字中，需要至少兩個有母語詞義的相似詞，才能組成情境選擇題。']
            return base

        options = [{'id': word['id'], 'sense_id': sense_id, 'label': word['lemma'],
                    'translation': sense['translation'], 'pos': word.get('pos'),
                    'reason': '原始例句在這個位置使用此字。'}]
        options.extend({'id': r['target_lexeme_id'], 'sense_id': None,
                        'label': r['target_word'], 'translation': r['translation'],
                        'pos': r.get('pos'),
                        'reason': f"{RELATIONS.get(r['relation'], r['relation'])}，但不是原始例句在此處使用的字。"}
                       for r in chosen)
        random.Random(f"{word['id']}:{sense_id}:similar-choice-v1").shuffle(options)
        return {**base, 'available': True, 'mode': 'similar_choice',
                'prompt': context['prompt'], 'example': context['example'],
                'options': options, 'correct_id': word['id'],
                'instruction': '閱讀情境句，從意思相近或拼字相似的選項中選出原句使用的單字。'}
    return base
