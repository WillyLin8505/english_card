"""Read-only boundary to the live lexicon. Never import its mutable app code."""
from contextlib import contextmanager
from pathlib import Path
import os
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from domain import merge_usages

ROOT = Path(__file__).resolve().parents[1]
# Most common usage of a spelling first: fully imported, translated, then most examples.
USAGE_ORDER = """(l.status='full') DESC,
    EXISTS(SELECT 1 FROM senses us JOIN sense_translations ut ON ut.sense_id=us.id
           WHERE us.lexeme_id=l.id AND ut.native_language=:native AND length(trim(ut.text))>0) DESC,
    (SELECT count(*) FROM examples ue WHERE ue.lexeme_id=l.id) DESC, l.id"""


def settings():
    return {**dotenv_values(ROOT / 'lexicon' / '.env'), **os.environ}


def make_engine():
    s = settings()
    url = s.get('CARD_PREVIEW_DATABASE_URL') or s.get('LEXICON_DATABASE_URL')
    if not url:
        url = URL.create('postgresql+psycopg', username=s.get('LEXICON_DB_USER', 'lexicon'),
                         password=s.get('LEXICON_DB_PASSWORD', ''),
                         host=s.get('LEXICON_DB_HOST', '127.0.0.1'),
                         port=int(s.get('LEXICON_DB_PORT', 5432)),
                         database=s.get('LEXICON_DB_NAME', 'lexicon'))
    return create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 5})


def rows(c, sql, **params):
    return [dict(r) for r in c.execute(text(sql), params).mappings()]


def image_allowed(row):
    license = (row.get('license_code') or '').upper().replace('-', ' ')
    return (row.get('review_status') == 'approved' and row.get('status') == 'ready'
            and bool(row.get('path')) and bool(row.get('page_url'))
            and row.get('safety_status') not in ('blocked', 'unsafe', 'rejected')
            and (license.startswith('CC0') or license == 'PUBLIC DOMAIN'
                 or license == 'CC BY' or license.startswith('CC BY '))
            and not any(x in license.split() for x in ('SA', 'NC', 'ND')))


class Repository:
    def __init__(self, engine=None):
        self.engine = engine or make_engine()
        self.media_root = Path(settings().get('LEXICON_MEDIA', ROOT / 'lexicon/media')).resolve()

    @contextmanager
    def read(self):
        with self.engine.connect() as c:
            c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
            c.execute(text("SET LOCAL statement_timeout = '8s'"))
            try:
                yield c
            finally:
                c.rollback()

    def catalog(self):
        with self.read() as c:
            return {'languages': rows(c, 'SELECT code FROM languages ORDER BY code'),
                    'pairs': rows(c, 'SELECT target_language,native_language FROM language_pairs ORDER BY id'),
                    'total': c.execute(text('SELECT count(*) FROM lexemes')).scalar(),
                    'read_only': True}

    def words(self, target, native, query='', offset=0, limit=40, scope='all'):
        where = """l.language=:target AND (l.lemma ILIKE :q ESCAPE '\\'
          OR CAST(l.id AS TEXT)=:exact OR EXISTS(
          SELECT 1 FROM senses s JOIN sense_translations t ON t.sense_id=s.id
          WHERE s.lexeme_id=l.id AND t.native_language=:native AND t.text ILIKE :q ESCAPE '\\'))"""
        if scope == 'recall_ready':
            where += " AND l.pos NOT IN ('unknown','') AND EXISTS(SELECT 1 FROM senses rs JOIN sense_translations rt ON rt.sense_id=rs.id WHERE rs.lexeme_id=l.id AND rt.native_language=:native AND length(trim(rt.text))>0 AND rt.text NOT LIKE '%�%')"
        elif scope == 'full':
            where += " AND l.status='full'"
        elif scope != 'all':
            raise ValueError('不支援的預覽範圍')
        params = dict(target=target, native=native, q='%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%', exact=query,
                      offset=offset, limit=limit)
        # One row per spelling (spec 07); a spelling matches when any of its POS lexemes does.
        with self.read() as c:
            total = c.execute(text('SELECT count(DISTINCT l.normalized) FROM lexemes l WHERE ' + where), params).scalar()
            keys = [r['normalized'] for r in rows(c, 'SELECT l.normalized FROM lexemes l WHERE ' + where
                    + " GROUP BY l.normalized ORDER BY bool_or(l.status='full') DESC,l.normalized LIMIT :limit OFFSET :offset", **params)]
            usages = rows(c, """SELECT l.id,l.normalized,l.lemma,l.pos,l.cefr,l.status,
                (SELECT t.text FROM senses s JOIN sense_translations t ON s.id=t.sense_id
                 WHERE s.lexeme_id=l.id AND t.native_language=:native ORDER BY s.ordinal,s.id LIMIT 1) AS meaning,
                (SELECT count(*) FROM examples e WHERE e.lexeme_id=l.id) AS example_count
                FROM lexemes l WHERE l.language=:target AND l.normalized=ANY(:keys) ORDER BY l.normalized,""" + USAGE_ORDER,
                target=target, native=native, keys=keys)
        groups = {}
        for u in usages:
            groups.setdefault(u['normalized'], []).append(u)
        items = []
        for key in keys:
            group = groups.get(key) or []
            if not group:
                continue
            first = group[0]
            items.append({'id': first['id'], 'lemma': first['lemma'], 'pos': first['pos'], 'cefr': first['cefr'],
                          'status': first['status'], 'meaning': first['meaning'],
                          'example_count': sum(u['example_count'] for u in group),
                          'lexeme_ids': [u['id'] for u in group], 'pos_list': [u['pos'] for u in group]})
        return dict(items=items, total=total, offset=offset, limit=limit)

    def usage_ids(self, lexeme_id, target, native):
        """Lexeme ids sharing this spelling, most common usage first."""
        with self.read() as c:
            ids = [r['id'] for r in rows(c, """SELECT l.id FROM lexemes l WHERE l.language=:target
                AND l.normalized=(SELECT normalized FROM lexemes WHERE id=:id AND language=:target)
                ORDER BY """ + USAGE_ORDER, id=lexeme_id, target=target, native=native)]
        if not ids:
            raise LookupError('找不到這個語言的詞條')
        return ids

    def entry(self, lexeme_id, target, native):
        """The single study card of a spelling: every POS usage merged."""
        return merge_usages([self.card(i, target, native) for i in self.usage_ids(lexeme_id, target, native)])

    def card(self, lexeme_id, target, native):
        with self.read() as c:
            found = rows(c, 'SELECT * FROM lexemes WHERE id=:id AND language=:target', id=lexeme_id, target=target)
            if not found:
                raise LookupError('找不到這個語言的詞條')
            word = found[0]
            args = dict(id=lexeme_id, native=native, target=target, lemma=word['normalized'])
            word['senses'] = rows(c, """SELECT s.*,d.text AS definition,d.source AS definition_source,
                t.text AS translation,t.source AS translation_source,t.is_ai,t.is_override
                FROM senses s LEFT JOIN definitions d ON d.sense_id=s.id AND d.language=:target
                LEFT JOIN sense_translations t ON t.sense_id=s.id AND t.native_language=:native
                WHERE s.lexeme_id=:id ORDER BY s.ordinal,s.id""", **args)
            word['examples'] = rows(c, """SELECT e.*,t.text AS translation,t.source AS translation_source,t.is_ai
                FROM examples e LEFT JOIN example_translations t ON t.example_id=e.id AND t.native_language=:native
                WHERE e.lexeme_id=:id ORDER BY e.ordinal,e.id""", **args)
            word['pronunciations'] = rows(c, 'SELECT * FROM pronunciations WHERE lexeme_id=:id ORDER BY is_default DESC,ordinal,id', **args)
            word['audio'] = rows(c, """SELECT DISTINCT a.* FROM audio_assets a JOIN pronunciations p ON p.audio_asset_id=a.id
                WHERE p.lexeme_id=:id AND a.status='ready' AND a.path IS NOT NULL ORDER BY a.id""", **args)
            word['forms'] = rows(c, 'SELECT * FROM forms WHERE lexeme_id=:id ORDER BY field,id', **args)
            word['relations'] = rows(c, """SELECT r.*,l.pos,l.cefr,t.text AS translation,t.source AS translation_source,t.is_ai
                FROM lexeme_relations r JOIN lexemes l ON l.id=r.target_lexeme_id
                LEFT JOIN relation_translations t ON t.relation_id=r.id AND t.native_language=:native
                WHERE r.lexeme_id=:id ORDER BY r.relation,r.ordinal,r.id""", **args)
            word['etymology'] = rows(c, """SELECT e.*,t.text AS translation,t.source AS translation_source,t.is_ai
                FROM etymologies e LEFT JOIN etymology_translations t ON t.lexeme_id=e.lexeme_id AND t.native_language=:native
                WHERE e.lexeme_id=:id""", **args)
            images = rows(c, """SELECT a.*,si.id AS sense_image_id,si.sense_id,si.review_status,si.semantic_score,si.alt_native,si.ordinal
                FROM sense_images si JOIN senses s ON s.id=si.sense_id JOIN image_assets a ON a.id=si.image_asset_id
                WHERE s.lexeme_id=:id ORDER BY si.ordinal,si.id""", **args)
            word['images'] = [i for i in images if image_allowed(i)]
            word['fields'] = rows(c, """SELECT field,status,missing,policy_version,resolved_at FROM field_values
                WHERE target_language=:target AND lemma=:lemma AND native_language IN ('*',:native) ORDER BY field""", **args)
            word['provenance'] = rows(c, """SELECT v.field,p.source,p.snapshot_id,p.strategy,p.processed_at,
                fc.license,fc.attribution,fc.source_record_id FROM field_values v
                JOIN field_provenance p ON p.field_value_id=v.id
                LEFT JOIN field_candidates fc ON fc.id=p.candidate_id
                WHERE v.target_language=:target AND v.lemma=:lemma AND v.native_language IN ('*',:native)
                ORDER BY v.field,p.position,p.id""", **args)
            releases = rows(c, """SELECT id,file_name,sha256,created_at FROM dictionary_releases
                WHERE target_language=:target AND native_language=:native AND status='ready'
                ORDER BY id DESC LIMIT 1""", **args)
            word['release'] = releases[0] if releases else None
            word['native_language'] = native
            word['data_mode'] = 'live_database'
            for item in word['audio']:
                item['url'] = '/api/media/audio/' + str(item['id'])
                item.pop('path', None)
            for item in word['images']:
                item['url'] = '/api/media/image/' + str(item['sense_image_id'])
                item.pop('path', None)
                item.pop('thumbnail_path', None)
            return word

    def media(self, kind, id):
        with self.read() as c:
            if kind == 'audio':
                result = rows(c, "SELECT * FROM audio_assets WHERE id=:id AND status='ready'", id=id)
            elif kind == 'image':
                result = rows(c, 'SELECT a.*,s.review_status FROM sense_images s JOIN image_assets a ON a.id=s.image_asset_id WHERE s.id=:id', id=id)
                result = [r for r in result if image_allowed(r)]
            else:
                result = []
        if not result or not result[0].get('path'):
            raise LookupError('媒體尚未就緒或未通過審核')
        r = result[0]
        path = (self.media_root / r['path']).resolve()
        if not path.is_relative_to(self.media_root) or not path.is_file():
            raise LookupError('找不到已驗證的本機媒體')
        return path

    def drag_exercise(self, word, sense_id):
        """Build a read-only drag exercise from reviewed image AI tag boxes.

        Tags are accepted only when their normalized word resolves to a full
        lexeme and its first sense has a native translation. The image itself
        has already passed ``image_allowed`` in ``card()``.
        """
        images = [im for im in word.get('images', []) if im.get('sense_id') == sense_id]
        if not images:
            return {'kind': 'drag', 'sense_id': sense_id, 'available': False,
                    'reasons': ['目前義項沒有已核准且可用的圖片']}
        pos_alias = {'adjective': 'adj', 'adverb': 'adv'}
        for image in images:
            tags = []
            for tag in image.get('tags') or []:
                label = str(tag.get('word', '')).strip().casefold()
                box = tag.get('box')
                if (not label or not isinstance(box, list) or len(box) != 4
                        or any(type(v) not in (int, float) for v in box)):
                    continue
                x1, y1, x2, y2 = box
                if min(box) < 0 or max(box) > 1 or x2 <= x1 or y2 <= y1:
                    continue
                tags.append((label, pos_alias.get(str(tag.get('pos', '')), tag.get('pos')), [x1, y1, x2-x1, y2-y1]))
            if not tags:
                continue
            labels = sorted({label for label, _, _ in tags})
            with self.read() as c:
                found = rows(c, """SELECT l.id,l.normalized,l.lemma,l.pos,l.cefr,s.id AS sense_id,t.text AS translation
                    FROM lexemes l
                    JOIN LATERAL (SELECT id FROM senses WHERE lexeme_id=l.id ORDER BY ordinal,id LIMIT 1) s ON true
                    JOIN sense_translations t ON t.sense_id=s.id AND t.native_language=:native
                    WHERE l.language=:target AND l.status='full' AND l.normalized=ANY(:labels)
                      AND length(trim(t.text))>0 AND t.text NOT LIKE '%�%'
                    ORDER BY l.normalized,l.id""", target=word['language'], native=word['native_language'], labels=labels)
            by_label = {}
            for row in found:
                by_label.setdefault(row['normalized'].casefold(), []).append(row)
            options, used = [], set()
            for label, tag_pos, box in tags:
                choices = by_label.get(label, [])
                row = next((item for item in choices if item['pos'] == tag_pos), choices[0] if choices else None)
                if not row or row['id'] in used:
                    continue
                used.add(row['id'])
                options.append({'id': row['id'], 'sense_id': row['sense_id'], 'label': row['lemma'],
                                'translation': row['translation'], 'pos': row['pos'],
                                'reason': '本機圖片辨識標籤與正式詞條相符', 'box': box})
                if len(options) == 5:
                    break
            if options:
                return {'kind': 'drag', 'sense_id': sense_id, 'available': True,
                        'mode': 'drag', 'image': image, 'options': options,
                        'instruction': '把每個單字拖到圖片中對應的位置。', 'reasons': []}
        return {'kind': 'drag', 'sense_id': sense_id, 'available': False,
                'reasons': ['圖片標籤框無法對應到有母語翻譯的正式詞條']}

    def templates(self, target, native):
        with self.read() as c:
            items = rows(c, 'SELECT * FROM card_templates WHERE target_language=:target AND native_language=:native ORDER BY id', target=target, native=native)
            for item in items:
                item['versions'] = rows(c, 'SELECT version,layout,published_at FROM card_template_versions WHERE template_id=:id ORDER BY version DESC', id=item['id'])
            return items
