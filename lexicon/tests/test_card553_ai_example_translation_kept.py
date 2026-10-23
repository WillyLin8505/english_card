"""問題回報 #589 (card #553): re-materializing keeps AI example translations that
live only in example_translations (ai_translate never writes field_values)."""

from __future__ import annotations

from sqlalchemy import select

from app import models as m
from app.materialize import materialize


def _seed(s):
    s.add(m.FieldValue(target_language="en", lemma="mie", native_language="zh-TW", field="pos",
                       status="complete", items=[{"key": "noun", "pos": "noun"}]))
    s.add(m.FieldValue(target_language="en", lemma="mie", native_language="zh-TW", field="definition",
                       status="complete", items=[{"key": "mie-noun", "sense_key": "mie-noun",
                                                  "pos": "noun", "gloss": "crumb"}]))
    s.add(m.FieldValue(target_language="en", lemma="mie", native_language="zh-TW", field="example",
                       status="complete", items=[{"key": "e1", "slot": "e1", "text": "A crumb.",
                                                  "sense_key": "mie-noun", "source": "tatoeba"}]))
    s.flush()


def test_ai_example_translation_survives_rematerialize(session):
    _seed(session)
    materialize(session, "en", "mie")
    ex = session.execute(select(m.Example)).scalar_one()
    session.add(m.ExampleTranslation(example_id=ex.id, native_language="zh-TW", text="一點碎屑。",
                                     source="ai", is_ai=True))
    session.add(m.ExampleTranslation(example_id=ex.id, native_language="ja", text="人手",
                                     source="x", is_ai=False))
    session.flush()
    materialize(session, "en", "mie")
    rows = {r.native_language: r for r in session.execute(select(m.ExampleTranslation)).scalars()}
    assert rows["zh-TW"].text == "一點碎屑。"
    assert "ja" not in rows  # non-AI rows absent from field_values still go
