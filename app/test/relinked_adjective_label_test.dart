// Owner 11/26: photo labels ribbed → rib 「肋骨」, textured → texture
// 「施加紋理」, molded → mold 「形成」. An adjective the pack knows only as
// a form of another word is left off the photo.
import 'package:flutter_test/flutter_test.dart';
import 'package:photo_english_app/models/learning_card.dart';
import 'package:photo_english_app/models/word_candidate.dart';
import 'package:photo_english_app/services/lexicon_pack.dart';
import 'package:photo_english_app/services/tagging_queue.dart';

WordCandidate _c(String word, String pos, {String? focus}) => WordCandidate(
    word: word,
    pos: pos,
    meaning: '',
    level: 'B2',
    levelSource: 'cefr-j',
    point: const LabelPoint(0.5, 0.5),
    focus: focus);

void main() {
  test('adjectives read as another word are dropped, the rest linked', () {
    Map<String, dynamic> entry(int id, String lemma, String pos, String zh,
            {List<String> forms = const [], String? card}) =>
        {
          'id': id,
          'lemma': lemma,
          'normalized': lemma,
          'pos': pos,
          'status': 'full',
          if (card != null) 'card': card,
          'senses': [
            {'id': id * 10, 'definition': lemma, 'native': zh}
          ],
          'forms': [
            for (final f in forms)
              {'field': 'verb_past_participle', 'form': f, 'normalized': f}
          ],
        };
    final pack = LexiconPack()
      ..loadJson({
        'target_language': 'en',
        'native_language': 'zh-TW',
        'lexemes': [
          entry(1, 'texture', 'verb', '施加紋理', forms: ['textured']),
          entry(2, 'linen', 'noun', '亞麻布'),
          entry(3, 'illuminate', 'verb', '照亮'),
          entry(4, 'illuminated', 'adj', '發光的', card: 'illuminate'),
          entry(5, 'woven', 'adj', '編織的'),
          entry(6, 'rib', 'noun', '肋骨'),
          entry(7, 'ribbed', 'adj', '有羅紋的', card: 'rib'),
        ],
      });
    final out = TaggingQueue.dropRelinkedAdjectives([
      _c('textured', 'adjective'),
      _c('linen', 'noun'),
      _c('illuminated', 'adjective'),
      _c('woven', 'adjective'),
      _c('ribbed', 'adjective'),
    ], pack: pack);
    expect(out.map((c) => c.word), ['linen', 'illuminate', 'woven']);
    expect(out.first.meaning, '亞麻布');
    // A harder-pass word the dictionary lacks is left off; a first-pass one stays.
    final harder = TaggingQueue.dropRelinkedAdjectives([
      _c('integumentary', 'adjective', focus: 'harder'),
      _c('golden retriever', 'noun'),
    ], pack: pack);
    expect(harder.map((c) => c.word), ['golden retriever']);
  });
}
