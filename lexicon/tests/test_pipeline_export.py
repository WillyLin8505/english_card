"""A headword through the pipeline, re-resolved after a policy change,
projected into the dictionary, and exported to SQLite."""

import hashlib
import json
import sqlite3

from sqlalchemy import select

from app import config, exporter, materialize, pipeline, policies, views
from app import models as m
from conftest import apple_data


def test_pipeline_stores_candidates_values_and_provenance(session, fakes):
    apple_data(fakes)
    reports = {r.field: r for r in pipeline.process_word(session, "en", "zh-TW", "apple", None,
                                                         "fill_missing")}
    assert reports["definition"].status == "complete"
    nd = reports["native_definition"]
    # s1 from Kaikki; only s2, which no dictionary translates, comes from AI, marked as AI
    assert nd.status == "complete"
    assert {i["slot"]: i["source"] for i in nd.items} == {"s1": "kaikki", "s2": "ai_translate"}
    assert [bool(i.get("ai")) for i in nd.items] == [False, True]
    assert nd.missing == []
    assert reports["example_translation"].status == "partial"
    assert reports["example_translation"].missing == ["ex2"]
    lex = session.execute(select(m.Lexeme).where(m.Lexeme.normalized == "apple")).scalars().all()
    assert [lx.pos for lx in lex] == ["noun"]
    # synonyms link to real lexemes (stubs until imported)
    rels = session.execute(select(m.LexemeRelation)).scalars().all()
    assert {r.target_word for r in rels} == {"orchard apple", "pome"}
    fv = session.execute(select(m.FieldValue).where(m.FieldValue.field == "synonyms")).scalar_one()
    prov = session.execute(select(m.FieldProvenance).where(
        m.FieldProvenance.field_value_id == fv.id)).scalars().all()
    assert [p.source for p in prov] == ["oewn", "kaikki"]


def test_named_gaps(session, fakes):
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    msgs = [i["message"] for i in views.word(session, "en", "zh-TW", "apple")["issues"]]
    assert "例句 #2 缺翻譯" in msgs
    assert "同義詞 orchard apple 缺繁體中文詞義" in msgs


def test_reresolve_after_policy_change_uses_stored_candidates(session, fakes):
    apple_data(fakes)
    fakes["kaikki"].data["verb_past"] = [({"form": "appled"}, "appled", "")]
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    ipa_before = session.execute(select(m.FieldValue).where(m.FieldValue.field == "ipa")).scalar_one()
    # Put "synonyms" in the order Kaikki → OEWN and re-resolve from storage
    p = policies.get(session, "en", "zh-TW", "synonyms")
    steps = sorted(p["steps"], key=lambda s: s["source"] != "kaikki")
    policies.put(session, "en", "zh-TW", "synonyms", {"strategy": p["strategy"],
                                                      "max_items": p["max_items"], "steps": steps})
    for a in fakes.values():
        a.calls.clear()
    r = pipeline.process_word(session, "en", "zh-TW", "apple", ["synonyms"], "reresolve")[-1]
    assert [i["source"] for i in r.items] == ["kaikki", "oewn"]
    assert not fakes["kaikki"].calls and not fakes["oewn"].calls  # nothing re-downloaded
    ipa_after = session.execute(select(m.FieldValue).where(m.FieldValue.field == "ipa")).scalar_one()
    assert ipa_after.items == ipa_before.items


def test_dry_run_writes_nothing(session, fakes):
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "dry_run")
    assert session.execute(select(m.FieldValue)).first() is None
    assert session.execute(select(m.FieldCandidate)).first() is None
    assert session.execute(select(m.Lexeme)).first() is None


def test_directions_do_not_overwrite_each_other(session, fakes):
    apple_data(fakes)
    fakes["kaikki"].data["native_definition"] = lambda ctx: [
        ({"sense_key": "s1", "text": "蘋果" if ctx.native == "zh-TW" else "pomme"}, "s1", "s1")]
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    pipeline.process_word(session, "en", "fr", "apple", None, "fill_missing")
    rows = {(t.native_language, t.text) for t in session.execute(select(m.SenseTranslation)).scalars()}
    assert ("zh-TW", "蘋果") in rows and ("fr", "pomme") in rows


def test_export_sqlite_with_manifest(session, fakes, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    assert rel.status == "ready", rel.error
    folder = tmp_path / rel.file_name
    db_file = folder / f"{rel.file_name}.sqlite"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["database"]["sha256"] == hashlib.sha256(db_file.read_bytes()).hexdigest()
    assert manifest["target_language"] == "en" and manifest["native_language"] == "zh-TW"
    assert manifest["schema_version"] == 4  # 4: approved sense pictures
    assert rel.file_name.startswith("language-data-en-zh-TW-")
    con = sqlite3.connect(db_file)
    lex = con.execute("SELECT id, pos FROM lexemes WHERE normalized = 'apple' AND pos = 'noun'"
                      " AND status = 'full'").fetchone()
    assert lex is not None
    senses = con.execute("SELECT s.definition, t.text FROM senses s LEFT JOIN sense_translations t"
                         " ON t.sense_id = s.id WHERE s.lexeme_id = ? ORDER BY s.ordinal",
                         (lex[0],)).fetchall()
    assert senses[0] == ("A round fruit.", "蘋果")
    assert con.execute("SELECT form FROM forms WHERE normalized = 'apples'").fetchone() == ("apples",)
    assert con.execute("SELECT count(*) FROM examples").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM example_translations").fetchone()[0] == 1
    relation_columns = {row[1] for row in con.execute("PRAGMA table_info(relations)")}
    assert {"target_cefr", "target_zipf", "rarity", "hide_by_default"} <= relation_columns
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert all(c["level"] != "error" for c in rel.checks)


def test_export_excludes_examples_without_verified_sense(session, fakes, tmp_path, monkeypatch):
    """Unresolved master examples must not be flattened into learner cards."""
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    fakes["tatoeba"].data["example_sentences"].append(
        ({"text": "Apple may also be a company name.", "tatoeba_id": 3}, "ex3", ""))
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")

    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    con = sqlite3.connect(tmp_path / rel.file_name / f"{rel.file_name}.sqlite")
    exported = {text for (text,) in con.execute("SELECT text FROM examples")}
    assert "I ate an apple today." in exported
    assert "The apple is red." in exported
    assert "Apple may also be a company name." not in exported


def test_failed_export_leaves_nothing(session, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)  # empty lexicon
    assert rel.status == "failed" and "沒有任何詞條" in rel.error
    assert list(tmp_path.iterdir()) == []


def test_export_with_active_snapshots_in_the_manifest(session, fakes, tmp_path, monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    session.add(m.SourceSnapshot(source="cmudict", language="en", version="master", status="ready",
                                 active=True, sha256="ab" * 32, details={},
                                 retrieved_at=datetime.now(timezone.utc)))
    session.flush()
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    assert rel.status == "ready", rel.error
    assert rel.manifest["source_snapshots"][0]["source"] == "cmudict"
    assert [p.name for p in tmp_path.iterdir()] == [rel.file_name]


def test_reresolve_asks_again_only_for_slots_nothing_answered(session, fakes):
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    # ex2 has no Tatoeba translation and AI had none the first time.
    asked = []

    def ai(ctx):
        wanted = ctx.memo.get(("missing_slots", "example_translation")) or []
        asked.extend(wanted)
        return [({"example_key": k, "text": "我們摘了一顆蘋果。", "ai": True}, k, k) for k in wanted]
    fakes["ai_translate"].data["example_translation"] = ai
    reports = {r.field: r for r in pipeline.process_word(
        session, "en", "zh-TW", "apple", ["example_translation"], "reresolve")}
    tr = reports["example_translation"]
    assert {i["slot"]: i["source"] for i in tr.items} == {"ex1": "tatoeba", "ex2": "ai_translate"}
    assert asked == ["ex2"], "ex1 is translated already: never sent to AI again"


def test_a_scene_phrase_no_dictionary_has_is_no_entry(session, fakes):
    pipeline.process_word(session, "en", "zh-TW", "in the kitchen", None, "fill_missing")
    assert not session.execute(select(m.Lexeme).where(
        m.Lexeme.normalized == "in the kitchen")).scalars().all()
    assert not session.execute(select(m.FieldValue).where(
        m.FieldValue.lemma == "in the kitchen")).scalars().all()


def test_app_pack_forms_follow_the_part_of_speech(session, fakes, tmp_path, monkeypatch):
    """問題回報 #85: each part of speech lists its own forms (apple the noun
    is not appled); a participle adjective also lists its verb's (grated)."""
    from app import app_pack
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    db_file = tmp_path / rel.file_name / f"{rel.file_name}.sqlite"
    con = sqlite3.connect(db_file)
    cols = [r[1] for r in con.execute("PRAGMA table_info(lexemes)")]
    row = dict(zip(cols, con.execute("SELECT * FROM lexemes WHERE normalized = 'apple'").fetchone()))
    noun_id, row["id"], row["pos"] = row["id"], 99999, "verb"
    con.execute(f"INSERT INTO lexemes ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [row[c] for c in cols])
    fcols = [r[1] for r in con.execute("PRAGMA table_info(forms)")]
    frow = dict(zip(fcols, con.execute("SELECT * FROM forms WHERE lexeme_id = ?", (noun_id,)).fetchone()))
    frow.update({"lexeme_id": 99999, "field": "verb_past", "form": "appled", "normalized": "appled"})
    frow.pop("id", None)
    con.execute(f"INSERT INTO forms ({','.join(frow)}) VALUES ({','.join('?' * len(frow))})",
                list(frow.values()))
    con.commit()
    con.close()
    lexemes = {x["pos"]: x for x in app_pack.build(db_file)["lexemes"] if x["normalized"] == "apple"}
    assert len(lexemes) == 2
    assert [f["field"] for f in lexemes["noun"]["forms"]] == ["noun_plural"]
    assert [f["field"] for f in lexemes["verb"]["forms"]] == ["verb_past"]


def test_a_participle_adjective_lists_its_verb_forms():
    from app import app_pack
    import sqlite3 as sq
    con = sq.connect(":memory:")
    lexemes = [{"id": 1, "normalized": "grated", "pos": "adj", "forms": []},
               {"id": 2, "normalized": "grated", "pos": "verb", "forms": [
                   {"field": "verb_base", "form": "grate", "normalized": "grate", "label": ""},
                   {"field": "verb_past", "form": "grated", "normalized": "grated", "label": ""}]},
               {"id": 3, "normalized": "happy", "pos": "adj", "forms": [
                   {"field": "adj_comparative", "form": "happier", "normalized": "happier", "label": ""}]},
               {"id": 4, "normalized": "happy", "pos": "verb", "forms": [
                   {"field": "verb_base", "form": "happy", "normalized": "happy", "label": ""},
                   {"field": "verb_past", "form": "happied", "normalized": "happied", "label": ""}]}]
    app_pack.share_forms({lx["id"]: lx for lx in lexemes})
    by = {(lx["normalized"], lx["pos"]): [f["form"] for f in lx["forms"]] for lx in lexemes}
    assert by[("grated", "adj")] == ["grate", "grated"]
    assert by[("happy", "adj")] == ["happier"]
    assert by[("happy", "verb")] == ["happy", "happied"]
    con.close()


def test_headword_forms_are_not_relation_words(session, fakes, tmp_path, monkeypatch):
    """問題回報 #19: apple's derived terms and synonyms never list apples."""
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    fakes["kaikki"].data["derived_terms"] = [({"word": "apples", "pos": "noun"}, "apples", ""),
                                             ({"word": "applesauce", "pos": "noun"}, "applesauce", "")]
    fakes["kaikki"].data["synonyms"] = [({"word": "Apples", "pos": "noun"}, "Apples", ""),
                                        ({"word": "pome", "pos": "noun"}, "pome", "")]
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    words = {r.target_word.lower() for r in session.execute(select(m.LexemeRelation)).scalars()}
    assert "applesauce" in words and "pome" in words
    assert "apples" not in words
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    con = sqlite3.connect(tmp_path / rel.file_name / f"{rel.file_name}.sqlite")
    exported = {w.lower() for (w,) in con.execute("SELECT target_word FROM relations")}
    con.close()
    assert "apples" not in exported and "applesauce" in exported


def test_british_ipa_is_the_default(session, fakes, tmp_path, monkeypatch):
    """問題回報 #20: 英式發音作為預設, a phonemic /…/ before a narrow […]."""
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    fakes["kaikki"].data["ipa"] = [
        ({"ipa": "/ˈæpəl/", "accent": ["AU"]}, "/ˈæpəl/", ""),
        ({"ipa": "[ˈapəl]", "accent": ["UK"]}, "[ˈapəl]", ""),
        ({"ipa": "/ˈapəl/", "accent": ["UK"]}, "/ˈapəl/", ""),
        ({"ipa": "/ˈæp.əl/", "accent": ["US"]}, "/ˈæp.əl/", ""),
    ]
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    con = sqlite3.connect(tmp_path / rel.file_name / f"{rel.file_name}.sqlite")
    rows = con.execute("SELECT value, accent, is_default FROM pronunciations WHERE kind = 'ipa'"
                       " ORDER BY ordinal").fetchall()
    con.close()
    assert rows[0] == ("/ˈapəl/", "UK", 1)
    assert [r[0] for r in rows] == ["/ˈapəl/", "/ˈæp.əl/", "/ˈæpəl/", "[ˈapəl]"]
    default = session.execute(select(m.Pronunciation).where(
        m.Pronunciation.kind == "ipa", m.Pronunciation.is_default.is_(True))).scalars().first()
    assert default.value == "/ˈapəl/"


def test_an_ipa_tagged_us_and_uk_counts_as_british(session, fakes, tmp_path, monkeypatch):
    """wind: /ˈwɪnd/ [US, UK] stays ahead of the verb's /wɑjnd/ [UK]."""
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    fakes["kaikki"].data["ipa"] = [({"ipa": "/ˈwɪnd/", "accent": ["US", "UK"]}, "/ˈwɪnd/", ""),
                                   ({"ipa": "/wɑjnd/", "accent": ["UK"]}, "/wɑjnd/", "")]
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    con = sqlite3.connect(tmp_path / rel.file_name / f"{rel.file_name}.sqlite")
    first = con.execute("SELECT value FROM pronunciations WHERE kind = 'ipa' AND is_default = 1"
                        ).fetchone()[0]
    con.close()
    assert first == "/ˈwɪnd/"
    assert materialize.main_accent(["AU", "CA", "US", "UK"]) == "UK"


def test_pronunciation_accent_label_prefers_british(session, fakes, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EXPORTS", tmp_path)
    apple_data(fakes)
    fakes["kaikki"].data["ipa"] = [({"ipa": "/ˈæpəl/", "accent": ["AU", "CA", "US", "UK"]},
                                    "/ˈæpəl/", "")]
    pipeline.process_word(session, "en", "zh-TW", "apple", None, "fill_missing")
    rel = exporter.export(session, "en", "zh-TW", include_audio=False)
    con = sqlite3.connect(tmp_path / rel.file_name / f"{rel.file_name}.sqlite")
    assert con.execute("SELECT accent FROM pronunciations WHERE kind = 'ipa'").fetchone()[0] == "UK"
    con.close()


def test_at_most_three_related_words_per_level_translated_first():
    from app.exporter import per_level
    def item(n, level, mean=True, hidden=False):
        return (n, {}, f"w{n}", None, None, {"text": "x"} if mean else None, {}, 4.0, level, hidden)
    found = [item(0, "A1", mean=False), item(1, "A1"), item(2, "A1"), item(3, "A1"),
             item(4, "A1"), item(5, "B1"), item(6, "A1", hidden=True)]
    kept = [x[0] for x in per_level(found)]
    assert kept == [1, 2, 3, 5, 6], "three translated A1 words, B1 untouched, hidden kept"


def test_a_later_etymologys_ipa_is_never_the_default():
    from app.materialize import british_first
    rows = [{"ipa": "/waɪnd/", "accent": ["UK"], "etymology": 2},
            {"ipa": "/wɪnd/", "accent": ["US"]}]
    assert british_first(rows)[0]["ipa"] == "/wɪnd/"


def test_unfit_relation_words_are_not_exported():
    """問題回報 #89: no 「shit」 under grass, no 「p t」/「law day」 sound-alikes."""
    from app.exporter import unfit_relation
    assert unfit_relation("related", "shit", "grass")
    assert unfit_relation("near_homophones", "p t", "patio")
    assert unfit_relation("near_homophones", "law day", "latte")
    assert unfit_relation("near_homophones", "natural high", "natural light")
    assert unfit_relation("similar_spelling", "an", "pan")
    assert not unfit_relation("similar_spelling", "pain", "pan")
    assert not unfit_relation("synonyms", "flat white", "latte")
    assert not unfit_relation("related", "lawn", "grass")
    assert unfit_relation("near_homophones", "st.", "street")
    assert unfit_relation("synonyms", "Good Book", "book")
    assert unfit_relation("synonyms", "📚", "book")
    assert unfit_relation("near_homophones", "heart to heart", "latte art")


def test_unfit_example_sentences_are_not_exported():
    from app.exporter import unfit_example
    assert unfit_example("Fucking hell, what idiot dare phone me?")
    assert unfit_example("Thanks God, Apple is dumping that Flash crap!")
    assert not unfit_example("Dick promised to come back by three o'clock.")
    assert not unfit_example("Kill two birds with one stone.")



def test_near_repeat_examples_take_no_place():
    from app.adapters import Candidate, Context
    ctx = Context("en", "zh-TW", "stone", "stone")
    ex = lambda t: Candidate("example_sentences", "en", {"text": t}, t)  # noqa: E731
    cands = [ex('"A rolling stone gathers no moss" is a saying.'),
             ex('"A rolling stone gathers no moss" is a proverb.'),
             ex("He threw a stone into the river."),
             ex("She threw a stone at the window.")]
    pipeline.level_candidates(cands, "example_sentences", ctx)
    assert [c.valid for c in cands] == [True, False, True, True]


def test_profane_chinese_is_left_out_of_meanings():
    """問題回報 #116: underdog 的「屌絲」、catfight 的「撕逼」; 逼真 stays."""
    from app.text import clean_native, offensive_native
    assert clean_native("失敗者、受迫者；弱者、處於劣勢的人、屌絲") == "失敗者、受迫者；弱者、處於劣勢的人"
    assert clean_native("打架、撕逼") == "打架"
    assert clean_native("撕逼") is None
    assert clean_native("逼真") == "逼真"
    assert not offensive_native("逼近、朦朧地出現")
