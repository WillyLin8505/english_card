import pathlib, re, json
p = pathlib.Path(r"D:/vibe_coding/english_card/app/build/web/main.dart.js")
d = p.read_text(encoding="utf-8", errors="replace")
pat = re.compile(r"(?:\\u[0-9a-fA-F]{4}){2,}")
found = set()
keys = ["例句", "翻譯", "顯示答案", "中文意思", "實用", "所有資訊", "想出這個字", "翻面", "展開", "查看更多"]
for m in pat.finditer(d):
    s = "".join(chr(int(m.group(0)[i + 2 : i + 6], 16)) for i in range(0, len(m.group(0)), 6))
    if any(k in s for k in keys):
        found.add(s)
out_dir = pathlib.Path(r"D:/vibe_coding/english_card/data")
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "ux_healthcheck_strings.json").write_text(
    json.dumps(sorted(found), ensure_ascii=False, indent=2), encoding="utf-8"
)
src = pathlib.Path(r"D:/vibe_coding/english_card/app/lib/screens/flashcard_screen.dart").read_text(encoding="utf-8")
i = src.find("case CardBackField.example")
j = src.find("case CardBackField.formsAndDerivations")
block = src[i:j]
(out_dir / "ux_example_block.txt").write_text(block, encoding="utf-8")
print("example_has_collapsed_true", "collapsed: true" in block or "collapsed:true" in block)
print("strings_n", len(found))
# Confirm _Block for examples: look between return _Block( and next );
start = block.find("return _Block(")
chunk = block[start : start + 400]
print("example_block_head", repr(chunk[:200]))
wd = pathlib.Path(r"D:/vibe_coding/english_card/app/lib/screens/word_detail_screen.dart").read_text(encoding="utf-8")
for label in ["實用例句", "查看更多例句", "更多單字資訊", "ExpansionTile"]:
    print(label, wd.find(label))
# front: examples?
front_i = src.find("class FlashcardFront")
front = src[front_i : front_i + 900]
print("front_mentions_example", "example" in front.lower() or "例句" in front)
(out_dir / "ux_front_snip.txt").write_text(front, encoding="utf-8")
# issues titles via API
import urllib.request
env = pathlib.Path(r"D:/vibe_coding/english_card/lexicon/.env").read_text(encoding="utf-8")
key = None
for line in env.splitlines():
    if line.strip().startswith("LEXICON_API_KEY"):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
req = urllib.request.Request(
    "http://127.0.0.1:8770/api/issues?status=needs_decision",
    headers={"X-API-Key": key},
)
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read().decode("utf-8"))
app_issues = [x for x in data.get("items", []) if x.get("area") == "app"]
summary = [{"id": x["id"], "title": x["title"], "kind": x["kind"]} for x in app_issues]
(out_dir / "ux_open_app_issues.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("app_needs_decision", summary)
