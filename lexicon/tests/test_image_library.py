"""Image list pagination and filters execute against the PostgreSQL test DB."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app import db, images, models as m


@pytest.fixture
def library_client(session):
    for index, (review, tag) in enumerate([
        ('pending', 'done'), ('approved', 'done'),
        ('pending', 'failed'), ('rejected', 'pending'),
        ('pending', 'done'),
    ]):
        word = f'word-{index}'
        lexeme = m.Lexeme(language='en', lemma=word, normalized=word, pos='noun')
        session.add(lexeme)
        session.flush()
        sense = m.Sense(lexeme_id=lexeme.id, sense_key=word, ordinal=0)
        asset = m.ImageAsset(source='wikimedia_commons', source_image_id=word,
                             license_code='CC0', status='ready', tag_status=tag,
                             safety_status='safe',
                             tags=[{'word': word, 'cefr': 'A1', 'score': 0.99}])
        session.add_all([sense, asset])
        session.flush()
        session.add(m.SenseImage(sense_id=sense.id, image_asset_id=asset.id,
                                review_status=review, role='representative'))
    session.flush()
    app = FastAPI()
    images.register(app, Depends(lambda: None))
    app.dependency_overrides[db.get_session] = lambda: session
    with TestClient(app) as client:
        yield client


def test_page_order_and_existing_list_contract(library_client):
    all_rows = library_client.get('/images').json()
    assert len(all_rows) == 5
    page1 = library_client.get('/images?limit=2').json()
    page2 = library_client.get('/images?limit=2&offset=2').json()
    page3 = library_client.get('/images?limit=2&offset=4').json()
    assert page1 + page2 + page3 == all_rows
    assert library_client.get('/images?offset=4').json() == all_rows[4:]
    assert library_client.get('/images?limit=2&offset=99').json() == []
    assert page1[0]['tags'][0]['cefr'] == 'A1'


def test_filtering_happens_before_pagination(library_client):
    approved = library_client.get('/images?review_status=approved').json()
    assert [r['normalized'] for r in approved] == ['word-1']
    failed = library_client.get('/images?tag_status=failed').json()
    assert [r['normalized'] for r in failed] == ['word-2']
    combined = library_client.get(
        '/images?review_status=pending&tag_status=done&limit=1&offset=1').json()
    assert [r['normalized'] for r in combined] == ['word-4']
    assert library_client.get('/images?review_status=approved&tag_status=failed').json() == []


@pytest.mark.parametrize('query', [
    'limit=0', 'limit=501', 'limit=-1', 'limit=abc', 'offset=-1',
    'review_status=unknown', 'tag_status=unknown',
])
def test_invalid_filters_are_rejected(library_client, query):
    assert library_client.get('/images?' + query).status_code == 422
