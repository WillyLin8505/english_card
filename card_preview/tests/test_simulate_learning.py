import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulate_learning import all_words, validate_exercise, cloze_suppression_candidates
from simulate_concurrent_learning import percentile


class SimulationTests(unittest.TestCase):
    def test_unavailable_cloze_audit_flags_fragments_without_declaring_them_valid(self):
        word = {'lemma': 'man', 'forms': [{'form': 'men'}], 'examples': [
            {'id': 1, 'sense_id': 10, 'text': 'Women live longer than men.', 'translation': '女人比男人長壽。'},
            {'id': 2, 'sense_id': 11, 'text': 'Women live longer than men.', 'translation': '其他義項'},
            {'id': 3, 'sense_id': 10, 'text': 'Women live longer than men.', 'translation': None},
            {'id': 4, 'sense_id': 10, 'text': 'Women and men greeted the man.', 'translation': '有別的詞形未遮罩'}]}
        result = cloze_suppression_candidates(word, {'id': 10})
        self.assertEqual([x['example_id'] for x in result], [1])
        self.assertEqual(result[0]['remaining_fragments'], ['men'])
        self.assertNotIn('available', result[0])
        word = {'lemma': 'apple', 'forms': [], 'examples': [
            {'id': 5, 'sense_id': 10, 'text': 'An apple is not an applecart.', 'translation': '複合字可能提示答案'}]}
        self.assertEqual(cloze_suppression_candidates(word, {'id': 10})[0]['example_id'], 5)

    def test_photo_choice_detects_wrong_option_already_tagged_on_picture(self):
        exercise = {'kind': 'photo_choice', 'sense_id': 10, 'available': True,
                    'correct_id': 1, 'image': {'tags': [
                        {'word': 'pears', 'cefrLemma': 'pear'}, {'word': 'apple'}]},
                    'options': [{'id': 1, 'label': 'apple'},
                                {'id': 2, 'label': 'Pear'}, {'id': 3, 'label': 'peach'}]}
        issues = validate_exercise({'id': 1, 'lemma': 'apple'}, {'id': 10},
                                   'photo_choice', exercise)
        self.assertIn('錯誤選項 Pear 同時是這張圖片的可見標籤', issues)
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
