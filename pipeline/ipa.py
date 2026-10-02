"""ARPABET (CMUdict) -> IPA, US pronunciation.

Spec section 6 lists CMUdict as the second source for 發音音標 after
Kaikki; CMUdict is ARPABET, not IPA, so this converts it. Stress marks go
before the stressed syllable's onset: the consonants just before the
vowel, as many as still form a valid English onset ("str", "pl").
"""

from __future__ import annotations

VOWELS = {
    "AA": "ɑ", "AE": "æ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "EY": "eɪ",
    "IH": "ɪ", "IY": "i", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
}
CONSONANTS = {
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ",
    "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "r", "S": "s",
    "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
ONSETS = {
    ("S", "T", "R"), ("S", "P", "R"), ("S", "K", "R"), ("S", "P", "L"), ("S", "K", "W"),
    ("P", "L"), ("P", "R"), ("B", "L"), ("B", "R"), ("T", "R"), ("D", "R"), ("K", "L"),
    ("K", "R"), ("K", "W"), ("G", "L"), ("G", "R"), ("F", "L"), ("F", "R"), ("TH", "R"),
    ("SH", "R"), ("S", "P"), ("S", "T"), ("S", "K"), ("S", "L"), ("S", "M"), ("S", "N"),
    ("S", "W"), ("T", "W"), ("D", "W"), ("P", "Y"), ("B", "Y"), ("K", "Y"), ("F", "Y"),
    ("M", "Y"), ("HH", "Y"), ("V", "Y"),
}


def _vowel(base: str, stress: str) -> str:
    if base == "AH":
        return "ʌ" if stress in "12" else "ə"
    if base == "ER":
        return "ɝ" if stress in "12" else "ɚ"
    return VOWELS[base]


def arpabet_to_ipa(phones: str) -> str | None:
    """'B AE1 L K AH0 N IY0' -> '/ˈbælkəni/'. None for unknown symbols."""
    items = []  # (symbol, ipa, stress mark or '')
    for p in phones.split():
        base, stress = (p[:-1], p[-1]) if p[-1].isdigit() else (p, "")
        if base in CONSONANTS:
            items.append((base, CONSONANTS[base], ""))
        elif base in VOWELS or base in ("AH", "ER"):
            mark = {"1": "ˈ", "2": "ˌ"}.get(stress, "")
            items.append((base, _vowel(base, stress), mark))
        else:
            return None
    vowel_idx = [i for i, it in enumerate(items) if it[0] in VOWELS or it[0] in ("AH", "ER")]
    marks: dict[int, str] = {}
    for n, i in enumerate(vowel_idx):
        mark = items[i][2]
        if not mark:
            continue
        start = vowel_idx[n - 1] + 1 if n > 0 else 0
        cluster = [it[0] for it in items[start:i]]
        if n == 0:
            at = 0
        else:
            take = 0
            for k in range(min(3, len(cluster)), 0, -1):
                if k == 1 or tuple(cluster[-k:]) in ONSETS:
                    take = k
                    break
            at = i - take
        if n == 0 and len(vowel_idx) == 1:
            continue  # one syllable: no stress mark, as dictionaries print it
        marks[at] = mark
    out = "".join(marks.get(i, "") + it[1] for i, it in enumerate(items))
    return f"/{out}/"
