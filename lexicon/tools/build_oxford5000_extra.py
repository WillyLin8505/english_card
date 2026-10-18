"""Build lexicon/backend/app/oxford5000_extra.json from the Oxford 5000 PDF text
(card #243, issue #220): the words the Oxford 5000 adds to the Oxford 3000 (B2-C1)
that CEFR-J/Octanove do not list. Usage: build_oxford5000_extra.py <oxford5000.pdf>"""
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[2]
POS = {"n": "noun", "v": "verb", "adj": "adj.", "adv": "adv.", "prep": "preposition", "conj": "conjunction",
       "pron": "pronoun", "det": "determiner", "exclam": "interjection", "number": "number"}
LINE = re.compile(r"^([A-Za-z][A-Za-z' -]*?) ((?:[a-z ]+\.(?:, )?)+) (A1|A2|B1|B2|C1|C2)$")


def main(pdf: str) -> None:
    text = "\n".join(p.get_text() for p in pymupdf.open(pdf))
    base = json.loads((ROOT / "app" / "assets" / "cefr_en.json").read_text(encoding="utf-8"))["words"]
    words = {}
    for line in text.splitlines():
        m = LINE.match(line.strip())
        if not m or m.group(1) in base:
            continue
        pos = {POS.get(p.strip(" .").split()[-1], "noun"): m.group(3) for p in m.group(2).split(",")}
        words[m.group(1)] = pos
    out = ROOT / "lexicon" / "backend" / "app" / "oxford5000_extra.json"
    out.write_text(json.dumps({"source": "The Oxford 5000 (Oxford University Press), words absent from CEFR-J/Octanove",
                               "words": words}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(len(words), "words ->", out)


if __name__ == "__main__":
    main(sys.argv[1])
