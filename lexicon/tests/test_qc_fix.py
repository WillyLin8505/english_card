"""P3: policy coverage, auto-apply threshold, rollback round-trip."""
from sqlalchemy import text

from app import db, qc_fix


def test_every_rule_has_a_policy():
    import inspect
    from app import qc
    src = inspect.getsource(qc.validate)
    import re
    rules = set(re.findall(r'v\["([a-z_]+\.[a-z_0-9]+)"\]', src))
    assert rules and rules <= set(qc_fix.POLICY), rules - set(qc_fix.POLICY)
    assert set(qc_fix.POLICY.values()) <= {"deterministic", "model", "human"}


def test_stub_cefr_fix_and_rollback(session):
    assert db.engine.url.database == 'lexicon_test'
    qc_fix.ensure_schema(session)
    session.execute(text("INSERT INTO lexemes (language, lemma, normalized, pos, status, cefr) "
                         "VALUES ('en','qcstub','qcstub','noun','stub','B2')"))
    run = qc_fix.new_run_id('test')
    assert qc_fix.fix_stub_cefr(session, run) >= 1
    assert session.execute(text("SELECT cefr FROM lexemes WHERE lemma='qcstub'")).scalar() is None
    assert qc_fix.rollback(session, run) >= 1
    assert session.execute(text("SELECT cefr FROM lexemes WHERE lemma='qcstub'")).scalar() == 'B2'


def test_sense_fallback_writes_pack_sense_and_rolls_back(session):
    """Card #213: persist the sense the pack already selected; keep the approval."""
    from app import models as m
    qc_fix.ensure_schema(session)
    lex = m.Lexeme(language="en", lemma="tree", normalized="tree", pos="noun", status="full")
    session.add(lex)
    session.flush()
    low = m.Sense(lexeme_id=lex.id, sense_key="low", ordinal=1, labels=["archaic"])
    main = m.Sense(lexeme_id=lex.id, sense_key="main", ordinal=0, labels=[])
    session.add_all([low, main])
    session.flush()
    image = m.ImageAsset(source="test", source_image_id="card213", safety_status="unchecked", status="ready")
    session.add(image)
    session.flush()
    binding = m.SenseImage(sense_id=low.id, image_asset_id=image.id, role="context",
                           review_status="approved", ordinal=0, alt_native={})
    taken = m.SenseImage(sense_id=main.id, image_asset_id=image.id, role="context",
                         review_status="approved", ordinal=1, alt_native={})
    other = m.ImageAsset(source="test", source_image_id="card213b", safety_status="unchecked", status="ready")
    session.add_all([binding, taken, other])
    session.flush()
    move = m.SenseImage(sense_id=low.id, image_asset_id=other.id, role="context",
                        review_status="approved", ordinal=0, alt_native={})
    session.add(move)
    session.flush()
    review = m.ImageReview(sense_image_id=move.id, decision="approved", note="自動採用（#34）")
    session.add(review)
    session.flush()
    pack = {"lexemes": [{"id": lex.id, "senses": [
        {"id": main.id, "native": "樹", "priority": "main"},
        {"id": low.id, "native": "古義", "priority": "low"},
    ]}], "catalog_images": [{"id": image.id, "tags": [
        {"lexeme_id": lex.id, "sense_id": main.id, "sense_id_before": low.id, "sense_fallback": True},
    ]}, {"id": other.id, "tags": [
        {"lexeme_id": lex.id, "sense_id": main.id, "sense_id_before": low.id, "sense_fallback": True},
    ]}]}
    run = qc_fix.new_run_id("test")
    done = qc_fix.fix_sense_fallback_bindings(session, run, pack)
    assert done["skipped_duplicate"] == 1
    assert done["rebound"] == 1
    assert session.execute(text("SELECT sense_id FROM sense_images WHERE id=:i"), {"i": binding.id}).scalar() == low.id
    assert session.execute(text("SELECT sense_id, review_status FROM sense_images WHERE id=:i"),
                           {"i": move.id}).one() == (main.id, "approved")
    assert session.execute(text("SELECT decision, note FROM image_reviews WHERE sense_image_id=:i"),
                           {"i": move.id}).one() == ("approved", "自動採用（#34）")
    assert qc_fix.rollback(session, run) == 1
    assert session.execute(text("SELECT sense_id FROM sense_images WHERE id=:i"), {"i": move.id}).scalar() == low.id
    again = qc_fix.fix_sense_fallback_bindings(session, qc_fix.new_run_id("test"), {"catalog_images": []})
    assert again == {"rebound": 0, "skipped_duplicate": 0, "skipped_missing_row": 0}


def test_model_suggestion_threshold(session):
    qc_fix.ensure_schema(session)
    session.execute(text("INSERT INTO lexemes (language, lemma, normalized, pos, status, cefr) "
                         "VALUES ('en','qcm','qcm','noun','full','C2')"))
    lid = session.execute(text("SELECT id FROM lexemes WHERE lemma='qcm'")).scalar()
    run = qc_fix.new_run_id('test')
    assert not qc_fix.propose(session, run, 'x', 'lexemes', lid, 'cefr', 'C2', 'B1', 'qwen', 0.79)
    assert session.execute(text("SELECT cefr FROM lexemes WHERE id=:i"), {"i": lid}).scalar() == 'C2'
    assert qc_fix.propose(session, run, 'x', 'lexemes', lid, 'cefr', 'C2', 'B1', 'qwen', 0.8)
    assert session.execute(text("SELECT cefr FROM lexemes WHERE id=:i"), {"i": lid}).scalar() == 'B1'
    assert session.execute(text("SELECT count(*) FROM qc_changes WHERE run_id=:r AND status='proposed'"),
                           {"r": run}).scalar() == 1
