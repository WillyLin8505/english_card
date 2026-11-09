"""Card #1011: /support page (App Review 1.5)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_support_page_and_route():
    html = (ROOT / 'docs' / 'support.html').read_text(encoding='utf-8')
    assert 'mailto:sssss971412@gmail.com' in html
    assert '/privacy' in html
    assert 'FAQ' in html and '常見問題' in html and 'Nous contacter' in html
    src = (ROOT / 'serve_app.py').read_text(encoding='utf-8')
    assert "'/support'" in src and "'support.html'" in src
