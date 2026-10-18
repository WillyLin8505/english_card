from owned_fixture import fixture_owned_ids
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repository import normalize_relation
from domain import live_exercise
from test_preview import word


class RelationVisibilityTests(unittest.TestCase):
    def test_frequency_and_explicit_flags_match_exporter(self):
        self.assertTrue(normalize_relation({'target_zipf': 2.2})['hide_by_default'])
        self.assertFalse(normalize_relation({'target_zipf': 2.5})['hide_by_default'])
        self.assertTrue(normalize_relation({'target_zipf': 4, 'detail': {'hide_by_default': True}})['hide_by_default'])
        self.assertTrue(normalize_relation({'detail': {'zipf': 1, 'cefr': 'C2'}})['hide_by_default'])
        self.assertEqual(normalize_relation({'detail': {'cefr': 'C2'}})['cefr'], 'C2')
        self.assertFalse(normalize_relation({'cefr': 'C2', 'target_zipf': 3})['hide_by_default'])

    def test_picture_and_similar_options_exclude_root_hidden_flag(self):
        w = word()
        w['images'] = [{'sense_id': 1, 'tags': [], 'url': '/image'}]
        w['relations'] = [
            {'target_word': 'hidden', 'target_lexeme_id': 2, 'translation': '罕用詞', 'relation': 'related', 'pos': 'noun', 'cefr': 'A1', 'strength': 10, 'hide_by_default': True},
            {'target_word': 'book', 'target_lexeme_id': 3, 'translation': '書本', 'relation': 'related', 'pos': 'noun', 'cefr': 'A1', 'strength': 1},
            {'target_word': 'shoe', 'target_lexeme_id': 4, 'translation': '鞋子', 'relation': 'related', 'pos': 'noun', 'cefr': 'A1', 'strength': 1},
        ]
        for kind in ('photo_choice', 'similar'):
            result = live_exercise(w, kind, 1, owned_lexeme_ids=fixture_owned_ids(w))
            self.assertTrue(result['available'], result)
            self.assertNotIn('hidden', [o['label'] for o in result['options']])


if __name__ == '__main__':
    unittest.main()
