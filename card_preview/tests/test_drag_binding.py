from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repository import Repository


@contextmanager
def fake_read():
    yield object()


class DragBindingTests(unittest.TestCase):
    def exercise(self, *, approved=True, explicit=None, tags=None):
        image = {'sense_id': 101, 'review_status': 'approved' if approved else 'pending',
                 'tags': [{'word': 'apple', 'pos': 'noun', 'box': [0, 0, .5, .5]},
                          {'word': 'stem', 'pos': 'noun', 'box': [.5, .5, 1, 1]},
                          {'word': 'leaf', 'pos': 'noun', 'box': [.5, 0, 1, .5]},
                          {'word': 'core', 'pos': 'noun', 'box': [0, .5, .5, 1]}]}
        if explicit is not None:
            image['tags'][0]['sense_id'] = explicit
        image['tags'].append({'word': 'peel', 'pos': 'noun', 'box': [.2, .2, .4, .4]})
        if tags is not None:  # apple, stem, leaf, core, peel: the first [tags]
            image['tags'] = image['tags'][:tags]
        word = {'id': 10, 'lemma': 'apple', 'normalized': 'apple', 'pos': 'noun',
                'language': 'en', 'native_language': 'zh-TW', 'images': [image],
                'senses': [{'id': 101, 'lexeme_id': 10, 'usage_pos': 'noun'}]}
        found = [{'id': 10, 'normalized': 'apple', 'lemma': 'apple', 'pos': 'noun', 'sense_id': 101, 'translation': '蘋果'},
                 {'id': 10, 'normalized': 'apple', 'lemma': 'apple', 'pos': 'noun', 'sense_id': 102, 'translation': '球形物'},
                 {'id': 11, 'normalized': 'stem', 'lemma': 'stem', 'pos': 'noun', 'sense_id': 201, 'translation': '家族血統'},
                 {'id': 11, 'normalized': 'stem', 'lemma': 'stem', 'pos': 'noun', 'sense_id': 202, 'translation': '莖'},
                 {'id': 12, 'normalized': 'leaf', 'lemma': 'leaf', 'pos': 'noun', 'sense_id': 301, 'translation': '葉子'},
                 {'id': 13, 'normalized': 'core', 'lemma': 'core', 'pos': 'noun', 'sense_id': 401, 'translation': '果核'},
                 {'id': 14, 'normalized': 'peel', 'lemma': 'peel', 'pos': 'noun', 'sense_id': 501, 'translation': '果皮'}]
        repo = Repository.__new__(Repository)
        repo.read = fake_read
        with patch('repository.rows', return_value=found):
            return repo.drag_exercise(word, 101)

    def test_reviewed_picture_binding_resolves_own_word_without_guessing_other_tags(self):
        exercise = self.exercise()
        self.assertTrue(exercise['available'])
        # stem has two meanings and no evidence for either: skipped, not guessed.
        self.assertEqual([(o['label'], o['sense_id'], o['translation']) for o in exercise['options']],
                         [('apple', 101, '蘋果'), ('leaf', 301, '葉子'), ('core', 401, '果核')])

    def test_a_drag_question_always_has_three_labels(self):
        self.assertEqual(len(self.exercise()['options']), 3)  # 4 usable: 3 of them
        self.assertFalse(self.exercise(tags=3)['available'], 'apple and leaf only: too few')

    def test_unapproved_binding_cannot_disambiguate_a_tag(self):
        self.assertFalse(self.exercise(approved=False)['available'])

    def test_explicit_target_tag_conflicting_with_picture_binding_is_skipped(self):
        self.assertFalse(self.exercise(explicit=102)['available'])


if __name__ == '__main__':
    unittest.main()
