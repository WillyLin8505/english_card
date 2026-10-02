from pathlib import Path
t = Path(r"D:\vibe_coding\english_card\app\lib\screens\database_library_screen.dart").read_text(encoding="utf-8")
for name in ["databaseTagLevel", "groupedDatabaseImageTags", "_groupedTileLabels", "_groupedTagSections"]:
    i = t.find(name)
    print(name, "at", i)
    if i >= 0:
        # line number
        print("  line", t[:i].count("\n")+1)
# overall brace balance
print("braces", t.count("{"), t.count("}"), "parens", t.count("("), t.count(")"))
# DatabaseImageScreen widget end
i = t.index("class DatabaseImageScreen")
j = t.index("class DatabaseWordScreen")
chunk = t[i:j]
print("ImageScreen braces", chunk.count("{"), chunk.count("}"))
print("--- end of ImageScreen ---")
print(chunk[-800:].encode("unicode_escape").decode())
