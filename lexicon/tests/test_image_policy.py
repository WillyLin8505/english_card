import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.images import allowed_license, check_url, plain


class ImagePolicyTests(unittest.TestCase):
    def test_permitted_and_forbidden_licenses(self):
        for value in ['CC0', 'CC0 1.0', 'Public domain', 'CC BY 2.0', 'CC BY 4.0']:
            self.assertTrue(allowed_license(value), value)
        for value in [None, '', 'unknown', 'CC BY-SA 4.0', 'CC BY-NC 4.0', 'CC BY-ND 4.0', 'CC BY 4.0 or unknown']:
            self.assertFalse(allowed_license(value), value)

    def test_network_targets_and_redirects_are_restricted(self):
        for url in ['https://upload.wikimedia.org/image.jpg', 'https://thumb.wikimedia.org/image.jpg']:
            self.assertEqual(check_url(url), url)
        for url in ['http://upload.wikimedia.org/a', 'https://evil.test/a', 'https://upload.wikimedia.org.evil.test/a',
                    'https://user:password@upload.wikimedia.org/a', 'https://127.0.0.1/a', 'https://upload.wikimedia.org:123/a']:
            with self.assertRaises(ValueError):
                check_url(url)

    def test_source_html_is_plain_text(self):
        self.assertEqual(plain('<a href="/">A &amp; B</a>'), 'A & B')


if __name__ == '__main__':
    unittest.main()
