"""Transactional, language-independent MVP card template publication."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from . import db, models as m
from .template_layout import default_layout, validate_layout


def published(s):
    row = s.execute(select(m.CardTemplateVersion, m.CardTemplate)
                    .join(m.CardTemplate, m.CardTemplate.id == m.CardTemplateVersion.template_id)
                    .where(m.CardTemplate.published_version == m.CardTemplateVersion.version)
                    .order_by(m.CardTemplateVersion.published_at.desc(), m.CardTemplateVersion.id.desc())
                    .limit(1)).first()
    if row is None:
        return None
    v, t = row
    return {'id': str(t.id), 'name': t.name, 'version': v.version, 'layout': v.layout}


def lock(s):
    # Serialize creation and publication across templates, including the first one.
    if s.bind.dialect.name == 'postgresql':
        s.execute(text('SELECT pg_advisory_xact_lock(170002)'))


def selected(s, template_id):
    if template_id == 'default':
        t = s.scalars(select(m.CardTemplate).order_by(m.CardTemplate.id)).first()
        if t is None:
            t = m.CardTemplate(target_language='*', native_language='*',
                               name='共用字卡版型', draft=default_layout())
            s.add(t)
            s.flush()
        return t
    try:
        t = s.get(m.CardTemplate, int(template_id))
    except ValueError:
        t = None
    if t is None:
        raise HTTPException(404, '找不到版型')
    return t


def snapshot(s, template_id='default'):
    t = selected(s, template_id)
    versions = s.scalars(select(m.CardTemplateVersion).where(
        m.CardTemplateVersion.template_id == t.id).order_by(m.CardTemplateVersion.version.desc()))
    return {'template_id': str(t.id), 'draft': t.draft, 'upstream': [],
            'published': published(s),
            'choices': [{'id': str(x.id), 'name': x.name} for x in
                        s.scalars(select(m.CardTemplate).order_by(m.CardTemplate.id))],
            'versions': [{'version': v.version, 'layout': v.layout,
                          'created': v.published_at.isoformat()} for v in versions]}


class LayoutBody(BaseModel):
    layout: dict


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    layout: dict | None = None


def checked(layout):
    try:
        return validate_layout(layout)
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(422, str(e)) from None


def register(app, auth):
    @app.get('/card-templates/published', dependencies=[auth])
    def get_published(s: Session = Depends(db.get_session)):
        return published(s)

    @app.get('/card-templates', dependencies=[auth])
    def get(template_id: str = 'default', s: Session = Depends(db.get_session)):
        lock(s)
        return snapshot(s, template_id)

    @app.post('/card-templates/create', dependencies=[auth])
    def create(body: CreateBody, s: Session = Depends(db.get_session)):
        lock(s)
        if not body.name.strip():
            raise HTTPException(422, '版型名稱不可空白')
        t = m.CardTemplate(target_language='*', native_language='*', name=body.name.strip(),
                           draft=checked(body.layout if body.layout is not None else default_layout()))
        s.add(t)
        s.flush()
        return snapshot(s, str(t.id))

    @app.post('/card-templates/save', dependencies=[auth])
    def save(body: LayoutBody, template_id: str = 'default', s: Session = Depends(db.get_session)):
        layout = checked(body.layout)
        lock(s)
        selected(s, template_id).draft = layout
        s.flush()
        return snapshot(s, template_id)

    @app.post('/card-templates/publish', dependencies=[auth])
    def publish(body: LayoutBody, template_id: str = 'default', s: Session = Depends(db.get_session)):
        layout = checked(body.layout)
        lock(s)
        t = selected(s, template_id)
        last = s.scalars(select(m.CardTemplateVersion.version).where(
            m.CardTemplateVersion.template_id == t.id).order_by(m.CardTemplateVersion.version.desc())).first() or 0
        # Only one active publication for every learning language.
        for other in s.scalars(select(m.CardTemplate)):
            other.published_version = None
        t.draft, t.published_version = layout, last + 1
        s.add(m.CardTemplateVersion(template_id=t.id, version=last + 1, layout=layout))
        s.flush()
        return snapshot(s, str(t.id))
