"""Card #753: 批量加入要學的單字 (admin) — split, classify, confirm."""

from app import bulk_add, models as m


def test_split_words_formats():
    t = "Apple, banana、cat\tdog;Egg\nfig\n\napple\n  ice   cream "
    assert bulk_add.split_words(t) == ["apple", "banana", "cat", "dog", "egg", "fig", "ice cream"]


def _seed(session):
    lex = m.Lexeme(language="en", lemma="brew", normalized="brew", pos="verb", status="full", cefr="B1")
    session.add(lex)
    session.flush()
    session.add(m.Form(lexeme_id=lex.id, field="verb_past", form="brewed", normalized="brewed",
                       source="t"))
    session.flush()


def test_classify_and_confirm(session, monkeypatch):
    _seed(session)
    monkeypatch.setattr(bulk_add.jobs, "create_shards",
                        lambda s, body, key=None: [type("J", (), {"id": 7})()])
    r = bulk_add.check(session, "brewed, brew\nzzzqx", "en", "zh-TW")
    st = {i["typed"]: i["status"] for i in r["items"]}
    # brewed leads to brew; the later typed brew is then the same word → one kept
    assert st["brewed"] == "variant" and st["brew"] == "duplicate" and st["zzzqx"] == "new"
    assert [i["word"] for i in r["items"] if i["typed"] == "brewed"] == ["brew"]
    out = bulk_add.confirm(session, [{"word": "brew"}, {"word": "zzzqx"}, {"word": "zzzqx"},
                                     {"word": "skip me", "include": False}], "en", "zh-TW")
    assert (out["added"], out["existing"], out["skipped"]) == (1, 1, 2)
    again = bulk_add.confirm(session, [{"word": "brew"}], "en", "zh-TW")
    assert again["wanted_total"] == 2
