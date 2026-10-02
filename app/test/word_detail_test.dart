// Not executed in the environment this project was scaffolded in (no
// Flutter/Dart SDK available there — network egress blocked the SDK
// download). Run `flutter test` yourself to actually exercise this;
// field-name correctness against the real pipeline output was
// cross-checked separately by grepping this model's json['...'] keys
// against pipeline/build_word_db.py's real output (see the project
// README for that check) rather than by running this file.

import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/word_detail.dart';

void main() {
  group('WordDetail.fromJson', () {
    test('parses the fields build_word_db.py actually emits', () {
      final json = {
        'word': 'example',
        'definitions': [
          {'pos': 'noun', 'gloss': 'a typical instance'},
        ],
        'definitions_source': 'wordnet',
        'ipa': null,
        'ipa_source': null,
        'arpabet': 'IH0 G Z AE1 M P AH0 L',
        'arpabet_source': 'cmudict',
        'word_audio_url': null,
        'word_audio_source': null,
        'synonyms': ['instance', 'illustration'],
        'synonyms_source': 'wordnet',
        'homophones': [],
        'homophones_source': null,
        'similar_spelling': ['ensample'],
        'similar_spelling_source': 'kaikki_wordlist',
        'inflections': [
          {'form': 'examples', 'label': 'plural'},
        ],
        'inflections_source': 'kaikki',
        'derivations': [
          {'word': 'exemplary', 'pos': 'adjective'},
        ],
        'derivations_source': 'wordnet',
        'root': 'exempl',
        'affixes': ['-um'],
        'morphology_source': 'kaikki',
        'example_sentences': [
          {
            'en': 'This is an example.',
            'zh': '這是一個例子。',
            'audio_url': 'https://x/a.mp3',
            'source': 'tatoeba',
            'zh_source': 'tatoeba',
            'audio_source': 'tatoeba',
          },
        ],
      };

      final detail = WordDetail.fromJson(json);

      expect(detail.word, 'example');
      expect(detail.definitions.single.gloss, 'a typical instance');
      expect(detail.definitionsSource, 'wordnet');
      expect(detail.arpabet, 'IH0 G Z AE1 M P AH0 L');
      expect(detail.synonyms, ['instance', 'illustration']);
      expect(detail.inflections.single.form, 'examples');
      expect(detail.derivations.single.word, 'exemplary');
      expect(detail.root, 'exempl');
      expect(detail.affixes, ['-um']);
      expect(detail.exampleSentences.single.zh, '這是一個例子。');
    });

    test('missing/empty fields degrade to empty collections, not crashes', () {
      final detail = WordDetail.fromJson({'word': 'zzz'});
      expect(detail.word, 'zzz');
      expect(detail.definitions, isEmpty);
      expect(detail.synonyms, isEmpty);
      expect(detail.ipa, isNull);
    });

    test('round-trips through toJson', () {
      final original = WordDetail.fromJson({
        'word': 'happy',
        'synonyms': ['glad'],
        'synonyms_source': 'wordnet',
      });
      final roundTripped = WordDetail.fromJson(original.toJson());
      expect(roundTripped.word, 'happy');
      expect(roundTripped.synonyms, ['glad']);
      expect(roundTripped.synonymsSource, 'wordnet');
    });
  });
}
