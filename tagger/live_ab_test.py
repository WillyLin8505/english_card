"""Small live regression suite for comparing tagger models through the HTTP API."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    {
        "name": "office",
        "path": ROOT / "app" / "assets" / "sample" / "album_office.jpg",
        "expected": {"laptop", "computer", "mouse", "cup", "mug", "desk", "table", "phone", "notebook", "plant"},
        "minimum_hits": 4,
    },
    {
        "name": "breakfast",
        "path": ROOT / "app" / "assets" / "sample" / "photo_breakfast.jpg",
        "expected": {"apple", "bread", "toast", "cup", "mug", "coffee", "plate", "knife", "spoon", "table"},
        "minimum_hits": 4,
    },
]


def request_json(url: str, key: str, body: bytes, content_type: str) -> tuple[dict, int]:
    request = urllib.request.Request(
        url,
        data=body,
        headers={"X-API-Key": key, "Content-Type": content_type},
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.loads(response.read())
    return payload, round((time.perf_counter() - started) * 1000)


def has_han(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def run(base_url: str, api_key: str) -> dict:
    result: dict = {"baseUrl": base_url, "images": [], "translations": []}
    with urllib.request.urlopen(f"{base_url}/health", timeout=10) as response:
        health = json.loads(response.read())
    result["model"] = health.get("model")
    result["health"] = health

    checks = 0
    passed = 0
    total_ms = 0
    # A harmless unique exclusion changes the cache key, ensuring both models
    # perform fresh inference instead of reusing an older sample result.
    cache_buster = f"abtest-{int(time.time())}"
    for sample in SAMPLES:
        query = urllib.parse.urlencode(
            {"level": "B1", "lang": "en", "native": "zh-TW", "exclude": cache_buster}
        )
        payload, wall_ms = request_json(
            f"{base_url}/tag?{query}", api_key, sample["path"].read_bytes(), "image/jpeg"
        )
        words = {
            str(item.get("word", "")).strip().lower()
            for item in payload.get("candidates", [])
            if str(item.get("word", "")).strip()
        }
        hits = sorted(words & sample["expected"])
        ok = len(hits) >= sample["minimum_hits"] and len(words) >= 6
        checks += 1
        passed += int(ok)
        total_ms += wall_ms
        result["images"].append(
            {
                "name": sample["name"],
                "ok": ok,
                "wallMs": wall_ms,
                "serverMs": payload.get("elapsedMs"),
                "hits": hits,
                "candidateCount": len(words),
                "words": sorted(words),
            }
        )

    translate_cases = [
        (
            "mixed",
            {
                "lang": "en",
                "native": "zh-TW",
                "kind": "sentence",
                "items": [
                    {"id": "s1", "text": "She sat on the bench."},
                    {"id": "s2", "text": "Tom likes tea better than coffee."},
                ],
            },
            lambda items: len(items) == 2 and all(has_han(i.get("text", "")) for i in items),
        ),
        (
            "gloss",
            {
                "lang": "en",
                "native": "zh-TW",
                "kind": "gloss",
                "items": [
                    {"id": "g1", "text": "A long seat for several people."},
                    {"id": "g2", "text": "Land used for growing crops or keeping animals."},
                ],
            },
            lambda items: len(items) == 2 and all(has_han(i.get("text", "")) for i in items),
        ),
        (
            "morphemes",
            {
                "lang": "en",
                "native": "zh-TW",
                "kind": "morphemes",
                "items": [{"id": "m1", "text": "unhappiness"}],
            },
            lambda items: len(items) == 1 and len(items[0].get("parts", [])) >= 2,
        ),
    ]
    for name, body, validator in translate_cases:
        payload, wall_ms = request_json(
            f"{base_url}/translate",
            api_key,
            json.dumps(body, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )
        items = payload.get("items", [])
        ok = bool(validator(items))
        checks += 1
        passed += int(ok)
        total_ms += wall_ms
        result["translations"].append(
            {"name": name, "ok": ok, "wallMs": wall_ms, "serverMs": payload.get("elapsedMs"), "items": items}
        )

    result["summary"] = {
        "passed": passed,
        "checks": checks,
        "passRate": round(passed / checks, 3),
        "totalWallMs": total_ms,
        "acceptable": passed == checks,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    api_key = (Path(__file__).resolve().parent / ".api_key").read_text(encoding="utf-8").strip()
    result = run(args.url.rstrip("/"), api_key)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
