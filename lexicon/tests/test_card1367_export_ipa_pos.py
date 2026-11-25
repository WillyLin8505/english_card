"""Card #1367 / issue #1802: the pack exporter wrote every ipa item of a headword to every lexeme,
so French `ne` (particle) showed the compass point NE's /nɔ.ʁɛst/ first. Same pos rule as materialize."""

from __future__ import annotations

import sqlite3

from app import exporter
from app.materialize import materialize


def _ipa(v, pos):
    return {"ipa": v, "key": f"{v}:{pos}:", "pos": pos, "slot": "", "accent": [], "source": "kaikki"}


def test_export_keeps_only_the_lexemes_own_pos_ipa(session, tmp_path):
    from app import models as m
    s = session
    s.add(m.FieldValue(target_language="en", lemma="ne", native_language="zh-TW", field="pos",
                       status="complete", items=[{"key": "particle", "pos": "particle"}]))
    s.add(m.FieldValue(target_language="en", lemma="ne", native_language="zh-TW", field="definition",
                       status="complete", items=[{"key": "ne-p", "sense_key": "ne-p", "pos": "particle",
                                                  "gloss": "not"}]))
    s.add(m.FieldValue(target_language="en", lemma="ne", native_language="zh-TW", field="ipa",
                       status="complete", items=[_ipa("/nɔ.ʁɛst/", "noun"), _ipa("/nə/", "particle")]))
    s.flush()
    materialize(s, "en", "ne")
    exporter._build(s, tmp_path / "pack.sqlite", "en", "zh-TW", None, False, tmp_path)
    con = sqlite3.connect(tmp_path / "pack.sqlite")
    vals = [r[0] for r in con.execute(
        "SELECT p.value FROM pronunciations p JOIN lexemes l ON l.id=p.lexeme_id "
        "WHERE l.normalized='ne' AND l.status='full' AND p.kind='ipa' ORDER BY p.ordinal")]
    assert vals == ["/nə/"]
