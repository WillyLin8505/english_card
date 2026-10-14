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
