from pathlib import Path
t = Path(r"D:\vibe_coding\english_card\app\lib\screens\database_library_screen.dart").read_text(encoding="utf-8")
print("len", len(t), "lines", t.count("\n"))
print("groupedDatabaseImageTags", "groupedDatabaseImageTags" in t)
print("_groupedTileLabels", "_groupedTileLabels" in t)
print("_groupedTagSections", "_groupedTagSections" in t)
print("databaseTagLevel", "databaseTagLevel" in t)
# last 80 lines
lines = t.splitlines()
for i, line in enumerate(lines[-80:], start=len(lines)-79):
    print(f"{i}:{line.encode('unicode_escape').decode()}")
