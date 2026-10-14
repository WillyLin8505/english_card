"""AI review for a small, verified word sample (問題回報 #184–#186).

    python lexicon/tools/quality_ai.py steep hinged rosemary ...   [--dry-run]

Uses local Ollama (qwen3-vl for pictures, same model for text):
  * images  - asks whether each approved sense picture really shows the word;
              "no" -> sense_images.review_status = 'rejected' (reversible).
  * senses  - asks which senses a learner needs; others go to
              quality/overrides.json low_priority_senses (only demotes).
  * examples- runs quality.example_flags; a flagged example is listed in
              rejected_examples and a new one is generated, re-validated and
              stored under overrides.json examples["word|pos"].
Every decision is logged to exports/quality/quality-ai-<date>.json."""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOME / "backend"))
from sqlalchemy import text  # noqa: E402

from app import config, db, quality  # noqa: E402

OLLAMA = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen3-vl:4b-instruct-q4_K_M"


def ask(prompt: str, image: Path | None = None) -> str:
    body = {"model": MODEL, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if image:
        body["images"] = [base64.b64encode(image.read_bytes()).decode()]
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    for _ in range(2):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["response"].strip()
        except OSError:
            continue
    return ""  # no answer: the caller keeps the current data


def image_shows(word: str, definition: str, path: Path) -> tuple[bool, str]:
    a = ask(f'Look at this photo. Is "{word}" (meaning: {definition[:160]}) clearly visible as a '
            f'main subject of the photo, so the photo is a good picture card for this word? Ignore '
            f'whether there is any text or label. Answer YES or NO first, then a short reason.', path)
    # No answer (timeout) keeps the picture.
    return (not a) or not a.upper().startswith("NO"), a[:200]


def main(words: list[str], dry: bool) -> None:
    overrides = quality.load_json("overrides.json")
    overrides.setdefault("low_priority_senses", [])
    overrides.setdefault("rejected_examples", [])
    overrides.setdefault("examples", {})
    log: dict = {"images": [], "senses": [], "examples": []}
    with db.session_scope() as s:
        for word in words:
            lexemes = s.execute(text("SELECT id, lemma, pos FROM lexemes WHERE normalized=:w AND status='full'"),
                                {"w": word}).all()
            for lx_id, lemma, pos in lexemes:
                senses = s.execute(text(
                    "SELECT se.id, se.ordinal, se.labels, d.text, t.text, t.is_ai FROM senses se"
                    " LEFT JOIN definitions d ON d.sense_id=se.id"
                    " LEFT JOIN sense_translations t ON t.sense_id=se.id AND t.native_language='zh-TW'"
                    " WHERE se.lexeme_id=:l ORDER BY se.ordinal"), {"l": lx_id}).all()
                if not senses:
                    continue
                defs = {sid: (d or "") for sid, _, _, d, _, _ in senses}
                # ---- images
                for si_id, sid, path, thumb in s.execute(text(
                        "SELECT si.id, si.sense_id, a.path, a.thumbnail_path FROM sense_images si"
                        " JOIN image_assets a ON a.id=si.image_asset_id"
                        " WHERE si.review_status='approved' AND si.sense_id = ANY(:ids)"),
                        {"ids": list(defs)}).all():
                    f = config.MEDIA / (thumb or path or "")
                    if not f.is_file():
                        continue
                    ok, why = image_shows(lemma, defs[sid], f)
                    log["images"].append({"word": lemma, "pos": pos, "sense_id": sid, "sense_image": si_id,
                                          "image": f.name, "keep": ok, "answer": why})
                    if not ok and not dry:
                        s.execute(text("UPDATE sense_images SET review_status='rejected' WHERE id=:i"),
                                  {"i": si_id})
                # ---- senses (only when there are several)
                if len(senses) > 1:
                    listing = "\n".join(f"{i + 1}. {d[:140]}" for i, (_, _, _, d, _, _) in enumerate(senses[:12]))
                    a = ask(f'English word "{lemma}" ({pos}). Senses:\n{listing}\n\nWhich sense numbers are '
                            f'common meanings a B1 learner should see? Rare, technical, slang, vulgar or '
                            f'obsolete senses are NOT. Reply with JSON only: {{"common": [numbers]}}')
                    m = re.search(r"\{.*\}", a, re.S)
                    try:
                        common = {int(x) for x in json.loads(m.group(0))["common"]} if m else None
                    except Exception:  # noqa: BLE001
                        common = None
                    if common:
                        common.add(1)  # the dictionary's first sense stays main
                        low = [senses[i][0] for i in range(min(len(senses), 12)) if i + 1 not in common]
                        log["senses"].append({"word": lemma, "pos": pos, "common": sorted(common),
                                              "low_ids": low})
                        for sid in low:
                            if sid not in overrides["low_priority_senses"]:
                                overrides["low_priority_senses"].append(sid)
                # ---- examples
                forms = [r[0] for r in s.execute(text("SELECT form FROM forms WHERE lexeme_id=:l"), {"l": lx_id})]
                exs = s.execute(text("SELECT id, text, sense_id FROM examples WHERE lexeme_id=:l ORDER BY ordinal"),
                                {"l": lx_id}).all()
                low_ids = set(overrides["low_priority_senses"])
                bad = []
                for ex_id, t, sid in exs:
                    fl = quality.example_flags(t, lemma, pos, forms)
                    if sid in low_ids:
                        fl.append("low_priority_sense")
                    if set(fl) & {"missing_lemma", "not_sentence", "pos_mismatch", "low_priority_sense"}:
                        bad.append((ex_id, t, fl))
                good = len(exs) - len(bad)
                for ex_id, t, fl in bad:
                    if ex_id not in overrides["rejected_examples"]:
                        overrides["rejected_examples"].append(ex_id)
                    log["examples"].append({"word": lemma, "pos": pos, "rejected": t, "flags": fl})
                key = f"{word}|{pos}"
                if bad and good == 0 and key not in overrides["examples"]:
                    main_sense = next(sid for sid, *_ in senses if sid not in low_ids)
                    for _ in range(3):
                        a = ask(f'Write one natural, complete English sentence (8-14 words) for learners '
                                f'that uses "{lemma}" as a {pos} meaning "{defs[main_sense][:160]}". Use '
                                f'everyday names or no names. Then translate it into natural Traditional '
                                f'Chinese as used in Taiwan. Reply JSON only: {{"en": "...", "zh": "..."}}')
                        m = re.search(r"\{.*\}", a, re.S)
                        try:
                            j = json.loads(m.group(0))
                        except Exception:  # noqa: BLE001
                            continue
                        if not quality.example_flags(j["en"], lemma, pos, forms):
                            new = {"id": None, "text": j["en"], "translation": j["zh"], "translation_ai": True,
                                   "level": None, "sense_id": main_sense, "source": "qwen-review",
                                   "license": None}
                            overrides["examples"][key] = [new]
                            log["examples"].append({"word": lemma, "pos": pos, "added": j})
                            break
        if dry:
            s.rollback()
    out = HOME / "exports" / "quality"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"quality-ai-{dt.datetime.now():%Y%m%d-%H%M}.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    if not dry:
        (quality.QUALITY_DIR / "overrides.json").write_text(
            json.dumps(overrides, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: len(v) for k, v in log.items()}, ensure_ascii=False))
    print(json.dumps(log, ensure_ascii=True)[:6000])


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args, "--dry-run" in sys.argv)