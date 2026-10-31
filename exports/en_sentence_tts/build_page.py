"""Build compare.html: the same English sentences from every voice source, audio embedded."""
import base64, html, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
picked = json.load(open(HERE / 'picked.json', encoding='utf-8'))
SOURCES = [
    ('human', '.mp3', '真人錄音', 'Tatoeba（CC 授權，作者 CK）', '免費；只有部分句子有'),
    ('azure_us', '.mp3', 'Azure 美式', 'en-US-AriaNeural', '雲端；免費每月 50 萬字，超過約 US$15／100 萬字'),
    ('azure_uk', '.mp3', 'Azure 英式', 'en-GB-SoniaNeural', '同上'),
    ('kokoro_us', '.wav', 'Kokoro 美式', 'af_heart（本機）', '免費，在這台電腦跑'),
    ('kokoro_uk', '.wav', 'Kokoro 英式', 'bf_emma（本機）', '免費，在這台電腦跑'),
    ('piper_us', '.wav', 'Piper 美式', 'en_US-lessac（本機）', '免費，最快、最小'),
]
def src(folder, ext, word):
    f = HERE / folder / f'{word}{ext}'
    mime = 'audio/mpeg' if ext == '.mp3' else 'audio/wav'
    return f'data:{mime};base64,' + base64.b64encode(f.read_bytes()).decode()
cards = []
for p in picked:
    zh = p.get('zh') or ''
    rows = ''.join(
        f'<div class="row"><div class="lab"><b>{name}</b><span>{html.escape(voice)}</span></div>'
        f'<audio controls preload="none" src="{src(folder, ext, p["word"])}"></audio></div>'
        for folder, ext, name, voice, _ in SOURCES)
    cards.append(f'<section class="card"><div class="w">{html.escape(p["word"])}</div>'
                 f'<div class="en">{html.escape(p["text"])}</div>'
                 f'<div class="zh">{html.escape(zh)}</div>{rows}</section>')
legend = ''.join(f'<li><b>{n}</b>：{html.escape(c)}</li>' for _, _, n, _, c in SOURCES)
page = f'''<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>英文例句發音比較</title><style>
:root{{--bg:#f6f6f8;--card:#fff;--fg:#1d1d1f;--mut:#6e6e73;--line:#e5e5ea;--acc:#0a66c2}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--card:#1c1c1e;--fg:#f2f2f2;--mut:#a1a1a6;--line:#333;--acc:#4ea1ff}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Noto Sans TC",sans-serif}}
main{{max-width:760px;margin:0 auto}} h1{{font-size:21px;margin:0 0 6px}} p,li{{color:var(--mut);font-size:14px}}
ul{{padding-left:20px;margin:4px 0 16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:0 0 14px}}
.w{{color:var(--acc);font-weight:700}} .en{{font-size:18px;margin:2px 0}} .zh{{color:var(--mut);font-size:14px;margin-bottom:8px}}
.row{{display:flex;align-items:center;gap:10px;border-top:1px solid var(--line);padding:6px 0}}
.lab{{width:170px;flex:none;display:flex;flex-direction:column}} .lab span{{color:var(--mut);font-size:12px}}
audio{{flex:1;min-width:0;height:36px}}
@media (max-width:520px){{.row{{flex-direction:column;align-items:stretch;gap:2px}} .lab{{width:auto;flex-direction:row;gap:8px;align-items:baseline}} audio{{width:100%}}}}
</style></head><body><main>
<h1>英文例句發音比較</h1>
<p>同一句英文用不同來源念。這 {len(picked)} 句都是英文詞庫裡現有的例句，而且 Tatoeba 上剛好有真人錄音，所以真人和合成可以直接比。</p>
<ul>{legend}</ul>
{''.join(cards)}
</main></body></html>'''
(HERE / 'compare.html').write_text(page, encoding='utf-8')
print((HERE / 'compare.html').stat().st_size // 1024, 'KB')
