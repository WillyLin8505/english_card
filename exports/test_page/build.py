"""Build the owner's test page (index.html). Every test is one layer in LAYERS, newest first;
add a layer here, run this script, then publish index.html to the same artifact."""
import base64, html, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TTS = HERE.parent / 'en_sentence_tts'
SOURCES = [
    ('human', '.mp3', '真人', 'Tatoeba 錄音'),
    ('azure_us', '.mp3', 'Azure 美式', 'AriaNeural'),
    ('azure_uk', '.mp3', 'Azure 英式', 'SoniaNeural'),
    ('kokoro_us', '.wav', 'Kokoro 美式', 'af_heart'),
    ('kokoro_uk', '.wav', 'Kokoro 英式', 'bf_emma'),
    ('piper_us', '.wav', 'Piper 美式', 'lessac'),
]
NOTES = {'happy': '這句原文少了 be（will happy），是 Tatoeba 原句的錯，詞庫裡也沒有中文。'}


def data_uri(path):
    mime = 'audio/mpeg' if path.suffix == '.mp3' else 'audio/wav'
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()


def sentence_audio_layer():
    rows = []
    for p in json.load(open(TTS / 'picked.json', encoding='utf-8')):
        keys = ''.join(
            f'<button class="key" type="button"><span class="k1">{name}</span><span class="k2">{html.escape(voice)}</span>'
            f'<audio preload="none" src="{data_uri(TTS / folder / (p["word"] + ext))}"></audio></button>'
            for folder, ext, name, voice in SOURCES)
        note = NOTES.get(p['word'])
        rows.append(f'<article class="item"><div class="word">{html.escape(p["word"])}</div>'
                    f'<p class="en">{html.escape(p["text"])}</p>'
                    f'<p class="zh">{html.escape(p.get("zh") or "")}</p>'
                    + (f'<p class="note">{html.escape(note)}</p>' if note else '')
                    + f'<div class="keys">{keys}</div></article>')
    return ('英文例句發音比較', '2026-10-31',
            '同一句英文用不同來源念，按鍵就播放，按另一個會自動換。這 6 句都是英文詞庫現有的例句。'
            '接下來的 50 句試聽（卡 #868）做好後會放在這一層上面。', ''.join(rows))


LAYERS = [sentence_audio_layer()]

STYLE = '''<title>單字卡測試頁</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Source+Serif+4:opsz,wght@8..60,500&display=swap">
<style>
/* Layout: one column; each test is a layer divided by a full-width heavy rule, items by hairlines */
:root { --bg:#f5f7f6; --ink:#17201d; --mut:#5c6b66; --line:#d3dcd8; --rule:#17201d; --key:#fff; --on:#0b6e5f; --on-ink:#fff;
  --body:"Noto Sans TC",system-ui,-apple-system,"PingFang TC",sans-serif; --en:"Source Serif 4",Georgia,serif; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#121816; --ink:#e8eeeb; --mut:#9aa8a3; --line:#2c3633; --rule:#e8eeeb; --key:#1b2320; --on:#3fc3ab; --on-ink:#08201b; color-scheme:dark } }
:root[data-theme="dark"] { --bg:#121816; --ink:#e8eeeb; --mut:#9aa8a3; --line:#2c3633; --rule:#e8eeeb; --key:#1b2320; --on:#3fc3ab; --on-ink:#08201b; color-scheme:dark }
body { background:var(--bg); color:var(--ink); font:16px/1.6 var(--body); }
main { max-width:760px; margin:0 auto; padding-block:28px 56px; padding-left:max(16px,env(safe-area-inset-left,0px)); padding-right:max(16px,env(safe-area-inset-right,0px)); }
h1 { font-size:24px; margin:0 0 4px; text-wrap:balance }
.lead { color:var(--mut); margin:0 0 24px; font-size:15px }
.layer { border-top:3px solid var(--rule); padding-block:16px 28px }
.layer-head { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:baseline; gap:4px 16px }
.layer h2 { font-size:20px; margin:0; text-wrap:balance }
.date { color:var(--mut); font-size:13px; font-variant-numeric:tabular-nums }
.intro { color:var(--mut); font-size:14px; margin:6px 0 8px; max-width:62ch }
.item { border-top:1px solid var(--line); padding-block:14px; display:grid; gap:4px }
.word { color:var(--on); font-weight:700; font-size:14px }
.en { font:500 20px/1.35 var(--en); margin:0 }
.zh { color:var(--mut); font-size:14px; margin:0 }
.zh:empty { display:none }
.note { font-size:13px; color:var(--mut); margin:0 }
.keys { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-top:8px }
.key { font:inherit; color:var(--ink); background:var(--key); border:1px solid var(--line); border-radius:8px; padding:8px 10px; text-align:left; cursor:pointer; display:grid; min-width:0 }
.key:focus-visible { outline:2px solid var(--on); outline-offset:2px }
.key.playing { background:var(--on); color:var(--on-ink); border-color:var(--on) }
.k1 { font-weight:500; font-size:14px }
.k2 { font-size:12px; opacity:.72; overflow-wrap:anywhere }
@media (max-width:480px) { .keys { grid-template-columns:repeat(2,minmax(0,1fr)) } }
</style>'''

SCRIPT = '''<script>
const keys = [...document.querySelectorAll('.key')];
function stop(k) { const a = k.querySelector('audio'); a.pause(); a.currentTime = 0; k.classList.remove('playing'); }
keys.forEach((k) => {
  const a = k.querySelector('audio');
  a.addEventListener('ended', () => k.classList.remove('playing'));
  k.addEventListener('click', () => {
    const was = k.classList.contains('playing');
    keys.forEach(stop);
    if (!was) { k.classList.add('playing'); a.play().catch(() => k.classList.remove('playing')); }
  });
});
</script>'''

body = ''.join(
    f'<section class="layer"><div class="layer-head"><h2>{html.escape(t)}</h2><span class="date">{d}</span></div>'
    f'<p class="intro">{html.escape(i)}</p>{c}</section>' for t, d, i, c in LAYERS)
page = (STYLE + '<main><h1>單字卡測試頁</h1><p class="lead">想試聽、想比較的東西都放這裡，一層一個測試，最新的在最上面。</p>'
        + body + '</main>' + SCRIPT)
(HERE / 'index.html').write_text(page, encoding='utf-8')
print((HERE / 'index.html').stat().st_size // 1024, 'KB')
