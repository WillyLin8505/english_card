import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulate_learning import all_words, validate_exercise
from simulate_concurrent_learning import percentile


class SimulationTests(unittest.TestCase):
    def test_all_words_follows_api_pagination(self):
        calls = []

        def fake_get(base, path, **query):
            calls.append(query['offset'])
            offset = query['offset']
            total = 205
            return {'total': total,
                    'items': [{'id': i} for i in range(offset, min(offset + 100, total))]}

        with patch('simulate_learning.get', side_effect=fake_get):
            words = all_words('http://preview', 'en', 'zh-TW')

        self.assertEqual(len(words), 205)
        self.assertEqual(calls, [0, 100, 200])

    def test_photo_recall_rejects_wrong_sense_image(self):
        word = {'id': 1, 'lemma': 'apple'}
        sense = {'id': 10, 'translation': '蘋果'}
        exercise = {'kind': 'photo_recall', 'sense_id': 10, 'available': True,
                    'images': [{'sense_id': 11}]}
        issues = validate_exercise(word, sense, 'photo_recall', exercise)
        self.assertIn('母語說明＋照片混入其他義項圖片', issues)

    def test_similar_accepts_canonical_id_for_merged_usage(self):
        word = {'id': 2, 'lemma': 'apple'}  # selected sense belongs to another POS usage
        sense = {'id': 10, 'translation': '蘋果'}
        exercise = {'kind': 'similar', 'sense_id': 10, 'available': True,
                    'correct_id': 1, 'prompt': 'I ate an ＿＿＿＿.',
                    'example': {'text': 'I ate an apple.', 'translation': '我吃了一顆蘋果。'},
                    'options': [
                        {'id': 1, 'label': 'apple', 'translation': '蘋果'},
                        {'id': 3, 'label': 'pear', 'translation': '梨子'},
                        {'id': 4, 'label': 'peach', 'translation': '桃子'}]}
        self.assertEqual(validate_exercise(word, sense, 'similar', exercise), [])

    def test_concurrent_latency_percentile_uses_observed_values(self):
        values = [10, 20, 30, 40, 50]
        self.assertEqual(percentile(values, .5), 30)
        self.assertEqual(percentile(values, .95), 40)
        self.assertEqual(percentile([], .95), 0)


if __name__ == '__main__':
    unittest.main()
