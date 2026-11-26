"""Give a Flutter web build versioned script URLs (owner 11/26: 「API 還是不對」).

Cloudflare rewrites serve_app's `Cache-Control: no-cache` on .js files to
`max-age=14400`, so a browser keeps an old main.dart.js for 4 hours after a
rebuild (a fix the owner couldn't see even after reloading). index.html is
left no-cache, so it now asks for `flutter_bootstrap.js?v=<hash>` and the
bootstrap for `main.dart.js?v=<hash>`: a new build is a new URL.

Run after every `flutter build web`:  python app/tool/web_cache_bust.py [build/web]
"""
import hashlib
import pathlib
import re
import sys

web = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                   pathlib.Path(__file__).resolve().parents[1] / 'build' / 'web')
main = (web / 'main.dart.js').read_bytes()
v = hashlib.sha1(main).hexdigest()[:10]

boot = web / 'flutter_bootstrap.js'
text = boot.read_text(encoding='utf-8')
text, n = re.subn(r'"mainJsPath":"main\.dart\.js(\?v=[0-9a-f]+)?"',
                  f'"mainJsPath":"main.dart.js?v={v}"', text)
assert n, 'mainJsPath not found in flutter_bootstrap.js'
boot.write_text(text, encoding='utf-8')
bv = hashlib.sha1(text.encode()).hexdigest()[:10]

index = web / 'index.html'
html = index.read_text(encoding='utf-8')
html, n = re.subn(r'src="flutter_bootstrap\.js(\?v=[0-9a-f]+)?"',
                  f'src="flutter_bootstrap.js?v={bv}"', html)
assert n, 'flutter_bootstrap.js script tag not found in index.html'
index.write_text(html, encoding='utf-8')
print(f'main.dart.js?v={v}  flutter_bootstrap.js?v={bv}')
