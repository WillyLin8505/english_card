"""Card #509 / 問題回報 #523: withdraw strip_cefr decisions the current lint no longer makes.

The proper_or_brand rule had fired on Title-Case lemmas (Buckle, Plateau) that
#460 later lower-cased; decisions.json kept the stale strip_cefr. The plan must
withdraw only lint-made decisions whose current flags carry no exclusion rule,
and keep card #318 spelling-variant decisions and anything outside the lint scope.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "card509_stale_exclusions",
    Path(__file__).resolve().parents[1] / "tools" / "card509_stale_exclusions.py")
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

DECISIONS = {"strip_cefr": [1, 2, 3, 4, 5, 6, 7], "redirect": {}, "set_cefr": {}}
# id -> (normalized, pos, status, db cefr)
ROWS = {1: ("buckle", "noun", "full", "B2"),      # stale: lint no longer flags it -> withdraw
        2: ("gaunt", "adj", "full", None),         # stale, DB cefr NULL -> restore from baseline
        3: ("brushstrokes", "noun", "full", None), # still inflected_form -> keep
        4: ("enquiry", "noun", "full", "C1"),      # card #318 variant -> keep
        5: ("acme", "noun", "full", None),         # not evaluated by this lint -> keep
        6: ("chen", "unknown", "stub", None),      # still person_name -> keep
        # 7: lexeme gone -> inert, keep
        }
FLAGS = {"brushstrokes|noun": {"inflected_form": "brushstroke"},
         "chen|unknown": {"person_name": "人名"},
         "buckle|noun": {"cefr_above_list": "B1"}}  # a level warning is not an exclusion
SCOPE = {"buckle|noun", "gaunt|adj", "brushstrokes|noun", "enquiry|noun", "chen|unknown"}
ORIGIN = {i: {"id": i, "rules": ["proper_or_brand"]} for i in (1, 2, 3, 5, 6, 7)}
BASELINE = {1: "B2", 2: "C2", 3: None, 4: "B1", 5: "B2"}


def test_plan_withdraws_only_stale_lint_decisions():
    items = tool.plan(DECISIONS, FLAGS, SCOPE, ROWS, ORIGIN, keep={4}, baseline=BASELINE)
    assert [e["id"] for e in items] == [1, 2]
    buckle, gaunt = items
    assert buckle["db_cefr"] == "B2" and buckle["restore_cefr"] is None
    assert gaunt["db_cefr"] is None and gaunt["restore_cefr"] == "C2"
    assert buckle["old_rules"] == ["proper_or_brand"]


def test_plan_keeps_card318_even_when_lint_made_it():
    items = tool.plan(DECISIONS, FLAGS, SCOPE, ROWS, {**ORIGIN, 4: {"id": 4, "rules": ["proper_or_brand"]}},
                      keep={4}, baseline=BASELINE)
    assert 4 not in {e["id"] for e in items}


def test_plan_needs_lint_origin_and_scope():
    # Not in origin: an owner-made decision is never withdrawn by the lint.
    items = tool.plan(DECISIONS, FLAGS, SCOPE, ROWS, {2: ORIGIN[2]}, keep=set(), baseline=BASELINE)
    assert [e["id"] for e in items] == [2]
    # Out of scope: absence of a flag is not evidence.
    items = tool.plan(DECISIONS, FLAGS, {"gaunt|adj"}, ROWS, ORIGIN, keep=set(), baseline=BASELINE)
    assert [e["id"] for e in items] == [2]
