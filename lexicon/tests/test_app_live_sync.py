"""Exercise real database → app JSON without touching the personal database."""
import json
import sys
from pathlib import Path

from sqlalchemy import select
from app import db, models as m, pipeline
from conftest import apple_data

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import serve_app


def test_live_pack_updates_without_export_release(session, fakes):
    # The fixture explicitly points to lexicon_test, never the user's lexicon.
    assert db.engine.url.database == 'lexicon_test'
    apple_data(fakes)
    pipeline.process_word(session, 'en', 'zh-TW', 'apple', None, 'fill_missing')
    session.commit()
    serve_app._cache.clear()
    body, etag = serve_app.live_pack('en', 'zh-TW')
    first = json.loads(body)
    assert any(s['native'] == '蘋果' for e in first['lexemes'] for s in e.get('senses', []))
    fv = session.execute(select(m.FieldValue).where(
        m.FieldValue.field == 'native_definition', m.FieldValue.lemma == 'apple')).scalar_one()
    items = json.loads(json.dumps(fv.items))
    items[0]['text'] = '自動同步測試蘋果'
    fv.items = items
    session.commit()
    # Expire only the short polling cache, preserving the content fingerprint.
    cached = serve_app._cache[('en', 'zh-TW')]
    serve_app._cache[('en', 'zh-TW')] = (0, *cached[1:])
    updated, new_etag = serve_app.live_pack('en', 'zh-TW')
    assert new_etag != etag
    assert '自動同步測試蘋果' in updated.decode()
    assert session.execute(select(m.DictionaryRelease)).first() is None
    serve_app._cache[('en', 'zh-TW')] = (0, *serve_app._cache[('en', 'zh-TW')][1:])
    assert serve_app.live_pack('en', 'zh-TW')[1] == new_etag


def test_catalog_matches_database_and_tracks_image_changes(session, fakes):
    assert db.engine.url.database == 'lexicon_test'
    apple_data(fakes)
    pipeline.process_word(session, 'en', 'zh-TW', 'apple', None, 'fill_missing')
    session.flush()
    sense = session.scalars(select(m.Sense)).first()
    asset = m.ImageAsset(source='test', source_image_id='test-image', status='ready', path='images/test.jpg')
    session.add(asset)
    session.flush()
    candidate = m.ImageCandidate(sense_id=sense.id, source='test', image_asset_id=asset.id)
    session.add(candidate)
    session.commit()
    serve_app._cache.clear()
    body, etag = serve_app.live_pack('en', 'zh-TW')
    result = json.loads(body)
    database_ids = set(session.scalars(select(m.Lexeme.id).where(m.Lexeme.language == 'en')))
    assert {word['id'] for word in result['lexemes']} == database_ids
    assert result['catalog_version'] == 1
    assert result['catalog_images'] == [], 'unreviewed candidates are not learner-facing'
    binding = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id,
                          role='representative', review_status='approved')
    session.add(binding)
    session.commit()
    serve_app._cache[('en', 'zh-TW')] = (0, *serve_app._cache[('en', 'zh-TW')][1:])
    updated, next_etag = serve_app.live_pack('en', 'zh-TW')
    assert next_etag != etag
    assert json.loads(updated)['catalog_images'][0]['tags'][0]['review_status'] == 'approved'
    session.delete(binding)
    session.delete(candidate)
    session.flush()
    session.delete(asset)
    session.commit()
    serve_app._cache[('en', 'zh-TW')] = (0, *serve_app._cache[('en', 'zh-TW')][1:])
    assert json.loads(serve_app.live_pack('en', 'zh-TW')[0])['catalog_images'] == []


def test_catalog_only_publishes_approved_formal_labels(session, fakes):
    apple_data(fakes)
    pipeline.process_word(session, 'en', 'zh-TW', 'apple', None, 'fill_missing')
    session.flush()
    sense = session.scalars(select(m.Sense)).first()
    word = session.get(m.Lexeme, sense.lexeme_id)
    asset = m.ImageAsset(
        source='test', source_image_id='review-filter', status='ready', path='images/test.jpg',
        tags=[
            {'word': word.normalized, 'pos': 'noun', 'point': [0.4, 0.5]},
            {'word': 'pomme', 'pos': 'noun', 'point': [0.2, 0.3]},
            {'word': 'hand', 'pos': 'noun', 'point': [0.8, 0.7]},
        ])
    session.add(asset)
    session.flush()
    rejected = m.SenseImage(sense_id=sense.id, image_asset_id=asset.id,
                            role='representative', review_status='rejected')
    session.add(rejected)
    session.flush()
    assert serve_app.catalog_snapshot(session, 'en')[1] == []

    rejected.review_status = 'approved'
    session.flush()
    image = serve_app.catalog_snapshot(session, 'en')[1][0]
    expected_tag = {
        'lexeme_id': word.id, 'sense_id': sense.id,
        'review_status': 'approved', 'origin': 'binding'}
    expected_label = {
        'word': word.lemma, 'pos': word.pos, 'point': [0.4, 0.5],
        'box': None, 'lexeme_id': word.id}
    band = (word.cefr or '').strip().upper()
    if band in {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}:
        expected_tag['cefr'] = band
        expected_label['cefr'] = band
    assert image['tags'] == [expected_tag]
    assert image['labels'] == [expected_label]
