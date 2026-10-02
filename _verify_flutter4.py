from pathlib import Path
t = Path(r"D:\vibe_coding\english_card\app\lib\screens\database_library_screen.dart").read_text(encoding="utf-8")
lines = t.splitlines()
for i in range(320, 560):
    print(f"{i+1}:{lines[i].encode('unicode_escape').decode()}")
