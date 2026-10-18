"""Isolated API tests: never migrate/truncate the owner's databases."""
import copy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import card_templates as ct, db, models as m
from app.template_layout import default_layout


def test_publication_is_global_immutable_and_validated():
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    m.Base.metadata.create_all(engine, tables=[m.CardTemplate.__table__, m.CardTemplateVersion.__table__])
    app = FastAPI()
    ct.register(app, __import__('fastapi').Depends(lambda: None))
    def session():
        with Session(engine) as s:
            yield s
            s.commit()
    app.dependency_overrides[db.get_session] = session
    with TestClient(app) as client:
        assert client.get('/card-templates/published').json() is None
        draft = client.get('/card-templates').json()
        layout = default_layout()
        layout['sections'][4]['limit'] = 2
        assert client.post('/card-templates/save', json={'layout': layout}).status_code == 200
        assert client.get('/card-templates/published').json() is None
        result = client.post('/card-templates/publish', json={'layout': layout}).json()
        assert result['published']['version'] == 1
        bad = copy.deepcopy(layout)
        bad['sections'][2]['visible'] = False
        assert client.post('/card-templates/publish', json={'layout': bad}).status_code == 422
        assert client.get('/card-templates/published').json()['version'] == 1
        layout2 = copy.deepcopy(layout)
        layout2['sections'][4]['limit'] = 4
        second = client.post('/card-templates/publish', json={'layout': layout2}).json()
        assert second['published']['version'] == 2
        assert second['versions'][1]['layout'] == layout
        other = client.post('/card-templates/create', json={'name': 'second'}).json()
        client.post('/card-templates/publish?template_id=' + other['template_id'], json={'layout': layout})
        assert client.get('/card-templates/published').json()['id'] == other['template_id']
        old = client.get('/card-templates?template_id=' + draft['template_id']).json()
        assert old['versions'][1]['layout'] == layout
        assert len(old['versions']) == 2
        # Language query cannot select a different publication.
        assert client.get('/card-templates?target=ja&native=en').json()['published'] == old['published']
