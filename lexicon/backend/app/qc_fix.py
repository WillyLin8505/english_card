"""P3: fixers, rollback log and `qc run` (QUALITY_SYSTEM_DESIGN.md §3.3–3.4).

Every validator rule maps to a policy:
  deterministic -> a fixer here, applied automatically and logged;
  model         -> P4 (local Qwen) via `propose()`; applied only at
                   confidence >= AUTO_APPLY, else left for a human;
  human         -> grouped into one local issue per rule.

Every change goes to qc_changes (run id, rule, entity, before, after,
source, confidence); `rollback(run_id)` restores the before values in
reverse order.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from sqlalchemy import text

from . import qc, quality

AUTO_APPLY = 0.8

POLICY = {
    "db.stub_has_cefr": "deterministic",
    "db.full_without_senses": "deterministic",
    # The fixer rebinds when the entry has a main sense with Chinese; what is
    # left has no such sense, so it needs a translation (model, P4).
    "photo_tag.sense_low_priority": "model",
    "photo_tag.sense_without_chinese": "model",
    "entry.full_without_senses": "deterministic",
    "entry.stub_in_pack": "deterministic",       # pack build: qc.strip_stubs
    "entry.stub_has_cefr": "deterministic",      # pack build: strip_stubs drops stubs
    "redirect.target_not_full": "deterministic",  # pack build: strip_stubs
    "relation.dangling_link": "deterministic",    # pack build: strip_stubs
    "photo_tag.on_redirect": "deterministic",     # pack build: fix_catalog_senses
    "photo_tag.level_differs_from_card": "deterministic",   # pack build
    "photo_label.level_differs_from_card": "deterministic",  # pack build
    "photo_tag.lexeme_not_full": "human",
    "photo_tag.sense_missing": "deterministic",   # pack build fallback
    "sense.main_without_chinese": "model",        # P4: translate
    "sense.main_is_ai": "model",                  # P4: verify AI translation vs dictionaries
    # 問題回報 #187: a dictionary meaning for the same slot, when there is one,
    # is swapped in deterministically (tools/fix_native_quality.py apply);
    # otherwise it needs a fresh translation (model, P4).
    "sense.native_empty": "model",
    "sense.native_has_latin": "model",
    "photo.fewer_than_3_tags": "model",           # P4: re-tag with the v12 prompt
    "entry.pos_unknown": "human",
    "pronunciation.ipa_is_arpabet": "human",      # #188: needs a look, not a blind convert
    "entry.full_without_ipa": "human",
    "entry.full_without_audio": "human",
}

DDL = """
CREATE TABLE IF NOT EXISTS qc_changes (
  id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL,
  rule TEXT NOT NULL,
  entity_table TEXT NOT NULL,
  entity_id BIGINT NOT NULL,
  column_name TEXT NOT NULL,
  before JSONB,
  after JSONB,
  source TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  status TEXT NOT NULL DEFAULT 'applied',  -- applied / proposed / rolled_back
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  rolled_back_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_qc_changes_run ON qc_changes (run_id);
CREATE INDEX IF NOT EXISTS ix_qc_changes_rule ON qc_changes (rule, status);
"""

# Only these (table, column) pairs may be changed by qc; rollback trusts them.
WRITABLE = {("lexemes", "cefr"), ("lexemes", "status"), ("sense_images", "sense_id")}


def ensure_schema(s) -> None:
    for stmt in DDL.strip().split(";"):
        if stmt.strip():
            s.execute(text(stmt))


def new_run_id(trigger: str = "manual") -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{trigger}"


def _set(s, run_id, rule, table, entity_id, column, before, after, source, confidence=1.0):
    assert (table, column) in WRITABLE, (table, column)
    s.execute(text(f"UPDATE {table} SET {column} = :v WHERE id = :id"), {"v": after, "id": entity_id})
    s.execute(text(
        "INSERT INTO qc_changes (run_id, rule, entity_table, entity_id, column_name, before, after, source, confidence) "
        "VALUES (:r, :rule, :t, :id, :c, CAST(:b AS jsonb), CAST(:a AS jsonb), :src, :conf)"),
        {"r": run_id, "rule": rule, "t": table, "id": entity_id, "c": column,
         "b": json.dumps(before), "a": json.dumps(after), "src": source, "conf": confidence})


def propose(s, run_id, rule, table, entity_id, column, before, after, source, confidence) -> bool:
    """P4 hook: a model-assisted change. Applied when confidence >= AUTO_APPLY,
    otherwise logged as 'proposed' for a human."""
    if confidence >= AUTO_APPLY:
        _set(s, run_id, rule, table, entity_id, column, before, after, source, confidence)
        return True
    s.execute(text(
        "INSERT INTO qc_changes (run_id, rule, entity_table, entity_id, column_name, before, after, source, confidence, status) "
        "VALUES (:r, :rule, :t, :id, :c, CAST(:b AS jsonb), CAST(:a AS jsonb), :src, :conf, 'proposed')"),
        {"r": run_id, "rule": rule, "t": table, "id": entity_id, "c": column,
         "b": json.dumps(before), "a": json.dumps(after), "src": source, "conf": confidence})
    return False


# ---- deterministic fixers --------------------------------------------------

def fix_stub_cefr(s, run_id) -> int:
    """A stub is not a learnable entry, so it carries no CEFR (R1/R2)."""
    rows = s.execute(text("SELECT id, cefr FROM lexemes WHERE status = 'stub' AND cefr IS NOT NULL")).all()
    if not rows:
        return 0
    s.execute(text(
        "INSERT INTO qc_changes (run_id, rule, entity_table, entity_id, column_name, before, after, source) "
        "SELECT :r, 'db.stub_has_cefr', 'lexemes', id, 'cefr', to_jsonb(cefr), 'null'::jsonb, 'qc-deterministic' "
        "FROM lexemes WHERE status = 'stub' AND cefr IS NOT NULL"), {"r": run_id})
    s.execute(text("UPDATE lexemes SET cefr = NULL WHERE status = 'stub' AND cefr IS NOT NULL"))
    return len(rows)


def fix_full_without_senses(s, run_id) -> int:
    """A 'full' entry with no senses is a stub (nothing to learn)."""
    rows = s.execute(text(
        "SELECT l.id FROM lexemes l WHERE l.status = 'full' AND NOT EXISTS "
        "(SELECT 1 FROM senses se WHERE se.lexeme_id = l.id)")).all()
    for (lid,) in rows:
        _set(s, run_id, "db.full_without_senses", "lexemes", lid, "status", "full", "stub", "qc-deterministic")
    return len(rows)


def sense_fallback_updates(pack: dict) -> list[dict]:
    """Tags whose pack already fell back to a main sense (fix_catalog_senses).

    The learner-facing pack rewrites these in memory. The database row still
    points at ``sense_id_before`` until a fixer writes the chosen sense back.
    """
    senses_by_id: dict = {}
    for lx in pack.get("lexemes") or []:
        for se in lx.get("senses") or []:
            if se.get("id") is not None:
                senses_by_id[se["id"]] = se
    updates = []
    for im in pack.get("catalog_images") or []:
        for tag in im.get("tags") or []:
            if not tag.get("sense_fallback"):
                continue
            new_id = tag.get("sense_id")
            old_id = tag.get("sense_id_before")
            if not new_id or new_id == old_id:
                continue
            before = senses_by_id.get(old_id)
            if before is None:
                rule = "photo_tag.sense_missing"
            elif not (before.get("native") or "").strip():
                rule = "photo_tag.sense_without_chinese"
            else:
                rule = "photo_tag.sense_low_priority"
            updates.append({
                "image_id": im["id"],
                "old_sense_id": old_id,
                "new_sense_id": new_id,
                "lexeme_id": tag.get("lexeme_id"),
                "rule": rule,
            })
    return updates


def fix_sense_fallback_bindings(s, run_id, pack: dict) -> dict:
    """Write each sense_fallback tag onto the main sense the pack already chose.

    Same write as the other photo-tag rebinds: approved ``sense_images.sense_id``
    only, logged in ``qc_changes``, skipped when that image is already bound to
    the chosen sense. Does not change review status, notes, or delete a row.
    """
    done = {"rebound": 0, "skipped_duplicate": 0, "skipped_missing_row": 0}
    for upd in sense_fallback_updates(pack):
        row = s.execute(text(
            "SELECT si.id, si.sense_id FROM sense_images si "
            "WHERE si.image_asset_id = :i AND si.sense_id = :s "
            "AND si.review_status = 'approved' ORDER BY si.id"),
            {"i": upd["image_id"], "s": upd["old_sense_id"]}).first()
        if not row or row[1] == upd["new_sense_id"]:
            done["skipped_missing_row"] += 1
            continue
        dup = s.execute(text(
            "SELECT 1 FROM sense_images WHERE image_asset_id = :i AND sense_id = :s AND id <> :id"),
            {"i": upd["image_id"], "s": upd["new_sense_id"], "id": row[0]}).first()
        if dup:
            done["skipped_duplicate"] += 1
            continue
        _set(s, run_id, upd["rule"], "sense_images", row[0], "sense_id",
             row[1], upd["new_sense_id"], "qc-deterministic")
        done["rebound"] += 1
    return done


def fix_photo_tag_senses(s, run_id, pack: dict, violations: dict) -> dict:
    """Rebind a photo tag whose sense is low priority or has no Chinese to
    the sense that best fits the photo among the entry's main senses with
    Chinese. No such sense -> left for the model (P4)."""
    by_id, redirects = qc._index(pack)
    images = {im["id"]: im for im in pack.get("catalog_images") or []}
    done = {"rebound": 0, "no_alternative": 0}
    for rule in ("photo_tag.sense_low_priority", "photo_tag.sense_without_chinese"):
        for image_id, lid in violations.get(rule, []):
            lx = by_id.get(redirects.get(lid, lid))
            im = images.get(image_id) or {}
            if not lx:
                continue
            tag = next((t for t in im.get("tags") or [] if t.get("lexeme_id") == lid), None)
            old = (tag or {}).get("sense_id_before") or (tag or {}).get("sense_id")
            context = set()
            for t in im.get("tags") or []:
                other = by_id.get(t.get("lexeme_id"))
                if other and other["id"] != lx["id"]:
                    context |= quality.tokens(other.get("lemma"))
            cands = [{"id": se["id"], "lexeme_pos": lx.get("pos"), "ordinal": n,
                      "definition": se.get("definition") or "", "native": se.get("native"),
                      "native_ai": se.get("native_ai"), "labels": se.get("labels") or [],
                      "low": se.get("priority") == "low"}
                     for n, se in enumerate(lx.get("senses") or [])]
            usable = [c for c in cands if (c["native"] or "").strip() and not c["low"]]
            if not usable:
                done["no_alternative"] += 1
                continue
            best, _, _ = quality.choose_sense(usable, context, None, lx.get("pos"))
            row = s.execute(text(
                "SELECT si.id, si.sense_id FROM sense_images si WHERE si.image_asset_id = :i "
                "AND si.sense_id = :s AND si.review_status = 'approved'"), {"i": image_id, "s": old}).first()
            if not row or row[1] == best["id"]:
                continue
            dup = s.execute(text("SELECT 1 FROM sense_images WHERE image_asset_id = :i AND sense_id = :s"),
                            {"i": image_id, "s": best["id"]}).first()
            if dup:
                continue
            _set(s, run_id, rule, "sense_images", row[0], "sense_id", row[1], best["id"], "qc-deterministic")
            done["rebound"] += 1
    return done


def apply_fixers(s, run_id, pack: dict, violations: dict) -> dict:
    ensure_schema(s)
    out = {"db.stub_has_cefr": fix_stub_cefr(s, run_id),
           "db.full_without_senses": fix_full_without_senses(s, run_id)}
    out.update({f"photo_tag.senses.{k}": v for k, v in fix_photo_tag_senses(s, run_id, pack, violations).items()})
    out.update({f"photo_tag.fallback.{k}": v
                for k, v in fix_sense_fallback_bindings(s, run_id, pack).items()})
    return out


def rollback(s, run_id: str) -> int:
    rows = s.execute(text(
        "SELECT id, entity_table, entity_id, column_name, before FROM qc_changes "
        "WHERE run_id = :r AND status = 'applied' ORDER BY id DESC"), {"r": run_id}).all()
    for cid, table, eid, col, before in rows:
        assert (table, col) in WRITABLE, (table, col)
        s.execute(text(f"UPDATE {table} SET {col} = :v WHERE id = :id"), {"v": before, "id": eid})
        s.execute(text("UPDATE qc_changes SET status = 'rolled_back', rolled_back_at = now() WHERE id = :id"),
                  {"id": cid})
    return len(rows)


def remaining_by_policy(violations: dict) -> dict:
    out: dict[str, dict] = {"deterministic": {}, "model": {}, "human": {}}
    for rule, items in violations.items():
        out[POLICY.get(rule, "human")][rule] = len(items)
    return out