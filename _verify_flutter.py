from pathlib import Path
t = Path(r"D:\vibe_coding\english_card\app\lib\screens\database_library_screen.dart").read_text(encoding="utf-8")
# Check structure around DatabaseImageScreen tags
idx = t.index("class DatabaseImageScreen")
chunk = t[idx:idx+4500]
# brace balance rough
print("open", chunk.count("{"), "close", chunk.count("}"))
# show from 圖片標籤 to attribution
a = t.index("Text('\u5716\u7247\u6a19\u7c64'")
b = t.index("MDecor.softCard(color: MColors.surfaceSoft)", a)
print("--- section ---")
print(t[a:b+80])
print("--- helpers tail ---")
print(t[t.index("String _groupedTileLabels"):t.index("String _groupedTileLabels")+500])
print("--- sections fn exists ---", "_groupedTagSections" in t)
# Check if old for-loop remnant
print("old flat loop left?", "for (final tag in databaseImageTags(image))" in t)
# Check DatabaseImageTile
ti = t.index("class DatabaseImageTile")
print(t[ti:ti+900])
