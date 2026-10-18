"""ECDICT (English→Chinese dictionary) before the AI in native-meaning policies."""

from app.adapters import Context
from app.adapters import ecdict

CSV = """word,phonetic,definition,translation,pos,collins,oxford,tag,bnc,frq,exchange,detail,audio
kettle,,,"n. 茶壶, 罐\\n[化] 釜体釜; 锅",,,,,0,0,,,
run,,,"n. 跑, 赛跑\\nvi. 跑, 奔跑, 跑步\\nrun的过去式和过去分词\\n[计] 运行",,,,,0,0,,,
software,,,n. [计] 软件,,,,,0,0,,,
hood,,,"n. 罩；风帽；（布质）面罩\\n[网络] 胡德；兜帽",,,,,0,0,,,
napkin,,,"n. 餐巾, 餐巾纸, 尿布",,,,,0,0,,,
nappy,,,"n. 尿布, 菜盆",,,,,0,0,,,
diaper,,,"n. 尿布",,,,,0,0,,,
"""


def _adapter(tmp_path, monkeypatch):
    (tmp_path / "ecdict.csv").write_text(CSV, encoding="utf-8")
    monkeypatch.setattr(ecdict, "CSV", tmp_path / "ecdict.csv")
    monkeypatch.setattr(ecdict, "INDEX", tmp_path / "ecdict.sqlite3")
    return ecdict.ECDict()


def test_meanings_keep_parts_of_speech_and_drop_domain_and_form_lines():
    assert ecdict.meanings("n. 跑, 赛跑\\nvi. 跑, 奔跑\\nrun的过去式和过去分词\\n[计] 运行") == [
        ("noun", ["跑", "赛跑"]), ("verb", ["跑", "奔跑"])]
    assert ecdict.meanings("n. 罩；风帽；（布质）面罩") == [("noun", ["罩", "风帽", "面罩"])]


def test_relation_words_get_their_part_of_speechs_first_meaning_in_taiwan_usage(
        tmp_path, monkeypatch):
    ed = _adapter(tmp_path, monkeypatch)
    ctx = Context("en", "zh-TW", "teapot", "teapot")
    ctx.resolved = {"pos": [{"pos": "noun"}],
                    "related": [{"word": "kettle", "pos": "noun"}, {"word": "run", "pos": "verb"},
                                {"word": "software"}, {"word": "unknownword"}]}
    got = {c.key: c.value["text"] for c in ed.lookup("related_native", ctx)}
    # 软件 → 軟體 (s2twp); a domain-only line is still a meaning once its tag is gone.
    assert got == {"kettle": "茶壺", "run": "跑、奔跑", "software": "軟體"}


def test_only_the_first_sense_of_each_part_of_speech_gets_a_native_definition(
        tmp_path, monkeypatch):
    ed = _adapter(tmp_path, monkeypatch)
    ctx = Context("en", "zh-TW", "run", "run")
    ctx.resolved = {"definition": [{"pos": "verb", "sense_key": "v1"},
                                   {"pos": "verb", "sense_key": "v2"},
                                   {"pos": "noun", "sense_key": "n1"}]}
    got = {c.slot: c.value["text"] for c in ed.lookup("native_definition", ctx)}
    assert got == {"v1": "跑、奔跑", "n1": "跑、賽跑"}


def test_a_synonym_pointer_sense_uses_the_named_words_meaning(tmp_path, monkeypatch):
    ed = _adapter(tmp_path, monkeypatch)
    ctx = Context("en", "zh-TW", "napkin", "napkin")
    ctx.resolved = {"definition": [
        {"pos": "noun", "sense_key": "table",
         "gloss": "A piece of cloth used at the table."},
        {"pos": "noun", "sense_key": "diaper",
         "gloss": "A nappy (UK), a diaper (American)."},
        {"pos": "noun", "sense_key": "scarf",
         "gloss": "A small scarf worn on the head by women when entering a church."},
    ]}
    got = {c.slot: c.value["text"] for c in ed.lookup("native_definition", ctx)}
    assert got["table"] == "餐巾"
    assert got["diaper"] == "尿布"
    assert "scarf" not in got


def test_ecdict_skips_a_low_priority_sense_and_fills_the_main_one(tmp_path, monkeypatch):
    ed = _adapter(tmp_path, monkeypatch)
    ctx = Context("en", "zh-TW", "run", "run")
    ctx.resolved = {"definition": [
        {"pos": "verb", "sense_key": "old", "labels": ["obsolete"], "gloss": "To flow."},
        {"pos": "verb", "sense_key": "main", "gloss": "To move quickly on foot."},
    ]}
    got = {c.slot: c.value["text"] for c in ed.lookup("native_definition", ctx)}
    assert got == {"main": "跑、奔跑"}


def test_seed_puts_ecdict_just_before_the_ai_without_a_new_policy_version(session):
    from sqlalchemy import select
    from app import models as m, policies
    p = session.execute(select(m.SourcePolicy).where(
        m.SourcePolicy.target_language == "en", m.SourcePolicy.native_language == "zh-TW",
        m.SourcePolicy.field == "related_native")).scalar_one()
    # An older policy: no ECDICT yet.
    for st in policies.steps_of(session, p):
        if st.source == "ecdict":
            session.delete(st)
    session.flush()
    version = p.version
    policies.seed(session)
    assert [st.source for st in policies.steps_of(session, p)] == [
        "lexicon", "kaikki", "ecdict", "ai_translate"]
    assert p.version == version
